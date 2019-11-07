# -*- coding: utf-8 -*-
"""metal_gen.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1RDjZb23LTOQRGsVTCEY9LJUA-2Etjd4e

Protein VAE

COLAB sucks
"""


import torch
import torch.nn.functional as nn
import torch.optim as optim
from torch.autograd import Variable
import torch.nn.functional as F
assert(torch.cuda.is_available())
print("Torch version:", torch.__version__)

import numpy as np
import argparse
import os
import timeit
        
from sklearn.metrics import accuracy_score
from sklearn.utils import shuffle
from sklearn.model_selection import train_test_split as tts

"""change parameters"""

args_dict = {
    "lr": 5e-4,
    "batch_size_train": 10000,
    "batch_size_test": 25,
    "num_epochs": 1000,
    "latent_dim": 16,
    "device": 0,
    "dataset": "nostruc"
}

cuda=True       # for training with gpu, make it true. For inference with cpu make false
load=False        # load in the model (default provided is 16 dimensional for nostruc data)
train=True      # Make true to train the model presuming you have the dataset
new_metal=True   # Make true to produce 'batch_size' samples of a given protein
                     # see the docs on github for description of how to do this
  
# CHANGE THIS
DATA_PATH = '/home/jason/deeplearning/data/protein-vae/assembled_data_mb.npy'

if cuda:
    if args_dict["dataset"]=="nostruc":    
        DATA = np.load(DATA_PATH)
    else:
        DATA = np.load('/scratch0/DeNovo/assembled_data_mbflip_fold.npy') #IGNORE 
    print("Full data set shape: {0}".format(DATA.shape))
    
    train_set, test_set = tts(DATA, test_size=0.15, shuffle=True)
    dev_train, dev_test = tts(DATA, train_size=0.15, test_size=0.1, shuffle=True)
    
    print("training set size: {0}".format(train_set.shape[0]))
    print("test set size: {0}".format(test_set.shape[0]))
    print("development training set size: {0}".format(dev_train.shape[0]))
    print("development test set size: {0}".format(dev_test.shape[0]))
    
    # CHANGE THIS, PICK DATA
    #data = dev_train
    #data_test = dev_test
    data = train_set
    data_test = test_set
    
    n=data.shape[0]
    X_dim = data.shape[1]
else:
    print("No DATA")
    if args_dict["dataset"]=="nostruc":
        X_dim=3088
    else:
        X_dim=4353

if cuda:
    os.environ["CUDA_VISIBLE_DEVICES"]=str(args_dict['device'])

#spec batch size
batch_size=args_dict['batch_size_train']
#learning rate
lr=args_dict['lr']
# layer sizes
hidden_size=[512,256,128,args_dict['latent_dim']]

class feed_forward(torch.nn.Module):
    def __init__(self, input_size, hidden_sizes, batch_size):
        super().__init__()
        
        self.input_size = input_size
        self.hidden_sizes = hidden_sizes
        self.batch_size = batch_size
           

        self.fc = torch.nn.Linear(input_size, hidden_sizes[0])  # 2 for bidirection 
        self.BN = torch.nn.BatchNorm1d(hidden_sizes[0])
        self.fc1 = torch.nn.Linear(hidden_sizes[0], hidden_sizes[1])
        self.BN1 = torch.nn.BatchNorm1d(hidden_sizes[1])
        self.fc2 = torch.nn.Linear(hidden_sizes[1], hidden_sizes[2])
        self.BN2 = torch.nn.BatchNorm1d(hidden_sizes[2])
        self.fc3_mu = torch.nn.Linear(hidden_sizes[2], hidden_sizes[3])
        self.fc3_sig = torch.nn.Linear(hidden_sizes[2], hidden_sizes[3])
        
        if args_dict["dataset"]=="struc":
            self.fc4 = torch.nn.Linear(hidden_sizes[3]+1273, hidden_sizes[2])
        else:        
            self.fc4 = torch.nn.Linear(hidden_sizes[3]+8, hidden_sizes[2])
        self.BN4 = torch.nn.BatchNorm1d(hidden_sizes[2])
        self.fc5 = torch.nn.Linear(hidden_sizes[2], hidden_sizes[1])
        self.BN5 = torch.nn.BatchNorm1d(hidden_sizes[1])
        self.fc6 = torch.nn.Linear(hidden_sizes[1], hidden_sizes[0])
        self.BN6 = torch.nn.BatchNorm1d(hidden_sizes[0])
        if args_dict["dataset"]=="struc":
            self.fc7 = torch.nn.Linear(hidden_sizes[0], input_size-1273)
        else:
            self.fc7 = torch.nn.Linear(hidden_sizes[0], input_size-8)

    def sample_z(self, mu, log_var):
        # Using reparameterization trick to sample from a gaussian
        
        if cuda:
            eps = torch.randn(self.batch_size, self.hidden_sizes[-1]).cuda()
        else:
            eps = torch.randn(self.batch_size, self.hidden_sizes[-1])
	
        return mu + torch.exp(log_var / 2) * eps
    
    def forward(self, x, code, struc=None):
        
        ###########
        # Encoder #
        ###########
        
        # get the code from the tensor
        # add the conditioned code
        if args_dict["dataset"]!="struc":
            x = torch.cat((x,code),1)
        else:
            x = torch.cat((x,code,struc),1)        
        # Layer 0
        out1 = self.fc(x)        
        out1 = nn.relu(self.BN(out1))
        # Layer 1
        out2 = self.fc1(out1)
        out2 = nn.relu(self.BN1(out2))
        # Layer 2
        out3 = self.fc2(out2)
        out3 = nn.relu(self.BN2(out3))
        # Layer 3 - mu
        mu   = self.fc3_mu(out3)
        # layer 3 - sig
        sig  = nn.softplus(self.fc3_sig(out3))        


        ###########
        # Decoder #
        ###########
        
        # sample from the distro
        sample= self.sample_z(mu, sig)
        # add the conditioned code
        if args_dict["dataset"]!="struc": 
            sample = torch.cat((sample, code),1)
        else:
            sample = torch.cat((sample, code, struc),1)
        # Layer 4
        out4 = self.fc4(sample)
        out4 = nn.relu(self.BN4(out4))
        # Layer 5
        out5 = self.fc5(out4)
        out5 = nn.relu(self.BN5(out5))
        # Layer 6
        out6 = self.fc6(out5)
        out6 = nn.relu(self.BN6(out6))
        # Layer 7
        out7 = nn.sigmoid(self.fc7(out6))
        
        return out7, mu, sig

"""Training:"""

# init the networks
if cuda:
    ff = feed_forward(X_dim, hidden_size, batch_size).cuda()
else:
    ff = feed_forward(X_dim, hidden_size, batch_size)

# change the loading bit here
if load: 
    ff.load_state_dict(torch.load("models/metal16_nostruc", map_location=lambda storage, loc: storage))


# Loss and Optimizer
solver = optim.Adam(ff.parameters(), lr=lr)
burn_in_counter = 0
tick = 0


# number of epochs
num_epochs=args_dict['num_epochs']

if train:
    
    patience = 100 # early stopping
    patience_counter = patience
    best_val_acc = -np.inf
    checkpoint_filename = 'checkpoint.pt' # save best model
    
    for its in range(num_epochs):
        
        #############################
        # TRAINING 
        #############################
        
        ff.train()
        scores=[]
        data=shuffle(data)
        
        if its%10 == 0:
          print("Epoch: {0}/{1}  Latent: {2}".format(its,num_epochs,hidden_size[-1]))
        
        start_time = timeit.default_timer()
        
        for it in range(n // batch_size):
        
            if args_dict["dataset"]=="nostruc":
                
                x_batch=data[it * batch_size: (it + 1) * batch_size]
                code = x_batch[:,-8:]
                x_batch = x_batch[:,:3080]

                if cuda:
                    X = torch.from_numpy(x_batch).cuda().type(torch.cuda.FloatTensor)
                    C = torch.from_numpy(code).cuda().type(torch.cuda.FloatTensor)
                else:
                    X = torch.from_numpy(x_batch).type(torch.FloatTensor)
                    C = torch.from_numpy(code).type(torch.FloatTensor)

                
            else:
                x_batch=data[it * batch_size: (it + 1) * batch_size]
                code = x_batch[:,-8:]
                structure = x_batch[:,3080:-8]
                x_batch = x_batch[:,:3080]

                if cuda:
                    X = torch.from_numpy(x_batch).cuda().type(torch.cuda.FloatTensor)
                    C = torch.from_numpy(code).cuda().type(torch.cuda.FloatTensor)
                    S = torch.from_numpy(structure).cuda().type(torch.cuda.FloatTensor) 
                else:
                    X = torch.from_numpy(x_batch).type(torch.FloatTensor)
                    C = torch.from_numpy(code).type(torch.FloatTensor)
                    S = torch.from_numpy(structure).type(torch.FloatTensor)  
    

            
            #turf last gradients
            solver.zero_grad()
            
            
            if args_dict["dataset"]=="struc":
            # Forward
                x_sample, z_mu, z_var = ff(X, C, S)
            else:
                x_sample, z_mu, z_var = ff(X, C)
            
    
                
            # Loss
            recon_loss = nn.binary_cross_entropy(x_sample, X, size_average=False) # by setting to false it sums instead of avg.
            kl_loss = 0.5 * torch.sum(torch.exp(z_var) + z_mu**2 - 1. - z_var)
            #kl_loss=KL_Div(z_mu,z_var,unit_gauss=True,cuda=True)
            kl_loss = kl_loss*burn_in_counter
            loss = recon_loss + kl_loss
            
            
            # Backward
            loss.backward()
        
            # Update
            solver.step()
            
            
            
            len_aa=140*22
            y_label=np.argmax(x_batch[:,:len_aa].reshape(batch_size,-1,22), axis=2)
            y_pred =np.argmax(x_sample[:,:len_aa].cpu().data.numpy().reshape(batch_size,-1,22), axis=2)
            
            
            # can use argmax again for clipping as it uses the first instance of 21
            # loop with 256 examples is only about 3 milliseconds                      
            for idx, row in enumerate(y_label):
                scores.append(accuracy_score(row[:np.argmax(row)],y_pred[idx][:np.argmax(row)]))
                
        elapsed = float(timeit.default_timer() - start_time)
        
        if its%10 == 0:
          print("Time: %.2fs" % (elapsed*10))
          print("Patience: {0}".format(patience))
          print("Tra Acc: {0}".format(np.mean(scores)))
                
        if its==(num_epochs-1):
            with open('latent_results_'+str(args_dict["dataset"])+'.txt', 'a') as f:
                f.write(str(args_dict['latent_dim'])+' train '+str(np.mean(scores)))


        if its>300 and burn_in_counter<1.0:
            burn_in_counter+=0.003
        
        
        #############################
        # Validation 
        #############################
        
        scores=[]
        
        ff.eval()
        for it in range(data_test.shape[0] // batch_size):
            x_batch=data_test[it * batch_size: (it + 1) * batch_size]

            if args_dict["dataset"]=="nostruc":

                x_batch=data[it * batch_size: (it + 1) * batch_size]
                code = x_batch[:,-8:]
                x_batch = x_batch[:,:3080]

                if cuda:
                    X = torch.from_numpy(x_batch).cuda().type(torch.cuda.FloatTensor)
                    C = torch.from_numpy(code).cuda().type(torch.cuda.FloatTensor)
                else:
                    X = torch.from_numpy(x_batch).type(torch.FloatTensor)
                    C = torch.from_numpy(code).type(torch.FloatTensor)


            else:
                
                x_batch=data[it * batch_size: (it + 1) * batch_size]
                code = x_batch[:,-8:]
                structure = x_batch[:,3080:-8]
                x_batch = x_batch[:,:3080]

                if cuda:
                    X = torch.from_numpy(x_batch).cuda().type(torch.cuda.FloatTensor)
                    C = torch.from_numpy(code).cuda().type(torch.cuda.FloatTensor)
                    S = torch.from_numpy(structure).cuda().type(torch.cuda.FloatTensor)
                else:
                    X = torch.from_numpy(x_batch).type(torch.FloatTensor)
                    C = torch.from_numpy(code).type(torch.FloatTensor)
                    S = torch.from_numpy(structure).type(torch.FloatTensor)


            if args_dict["dataset"]=="struc":
            # Forward
                x_sample, z_mu, z_var = ff(X, C, S)
            else:
                x_sample, z_mu, z_var = ff(X, C)

                            

        
            len_aa=140*22
            y_label=np.argmax(x_batch[:,:len_aa].reshape(batch_size,-1,22), axis=2)
            y_pred =np.argmax(x_sample[:,:len_aa].cpu().data.numpy().reshape(batch_size,-1,22), axis=2)

            for idx, row in enumerate(y_label):
                scores.append(accuracy_score(row[:np.argmax(row)],y_pred[idx][:np.argmax(row)]))
        
        
        if its%10 == 0:
          acc = np.mean(scores)
          print("Val Acc: {0}".format(acc))
          print()
        
        if acc > best_val_acc:           
          torch.save(ff.state_dict(), checkpoint_filename)
          best_val_acc = acc
          patience_counter = patience               
        else:
          patience_counter -= 1
          if patience_counter <= 0:
                ff.load_state_dict(torch.load(checkpoint_filename))
                break
          
        if its==(num_epochs-1):
            with open('latent_results_'+str(args_dict["dataset"])+'.txt', 'a') as f:
                f.write(str(args_dict['latent_dim'])+' test '+str(np.mean(scores)))



# # saves if its running on gpu          
# if cuda:
#     torch.save(ff.state_dict(), 'metal'+str(args_dict['latent_dim'])+"_"+str(args_dict['dataset']))

"""RESULT: (dev set 15% train, 10% validation)

300 epochs (~15 min)

Tra Acc: 0.5220075942567366

Val Acc: 0.5241073249741528
"""