import sys
import os
import pprint
import math
import PIL

import numpy as np

import torch
from torch import nn
from torch import optim
from torch.utils.data import DataLoader

import torchvision
import torchvision.transforms as transforms
import torchvision.utils as vutils

# import tensorboard
# from tensorboard import SummaryWriter
from torch.utils.tensorboard import SummaryWriter

sys.path.append('..')

import data_utils
from data_utils import FlyingChairsSR

import networks
from networks import SRResNet

import utils

import pdb

# for maintaining consistent training/validation splits
torch.manual_seed(3607)

# training parameters
batch_size = 8
lr = 1e-4
start_epoch = 0
max_epochs = 100
log_interval = 10
viz_interval = 100
save_interval = 1

#salman's addition
expt_folder = '/mnt/data/salman/LenslessDesign/models/srfnet/'
logdir = expt_folder + 'runs/'

# visualizations
writer = SummaryWriter(log_dir=logdir)

# data 
nvset = 500
training_set = 'flying_chairs'
dataset = FlyingChairsSR('/mnt/data/salman/LenslessDesign/datasets/FlyingChairs_release/data/',
        input_scale=16, target_scale=4, crop_dim=(256, 256))
trainset, validset = torch.utils.data.random_split(dataset, (dataset.__len__() - nvset, nvset))

torch.manual_seed(3607 + start_epoch)
trainloader = DataLoader(trainset, batch_size=batch_size, num_workers=4, shuffle=True)
validloader = DataLoader(validset, batch_size=10, num_workers=4)

# validation hacks
bicubic_transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((64, 64), PIL.Image.BICUBIC),
    transforms.ToTensor()
    ])

# setup network
model = SRResNet().cuda()
if start_epoch > 0:
    checkpoint_file = os.path.join(expt_folder, 'states', training_set,'srresnet_%d.pkl' % start_epoch)
    model.load_state_dict(torch.load(checkpoint_file))
    print('Loading network')

optimizer = optim.Adam(model.parameters(), lr=lr)
# scheduler = optim.lr_scheduler.StepLR(optimizer, 1e5, gamma=0.5)
criterion = nn.MSELoss()

n_iter = start_epoch * math.ceil(float(trainset.__len__()) / batch_size)

model.train()
for epoch in range(start_epoch, max_epochs):

    for low_res, high_res in trainloader:

        low_res = low_res.cuda()
        high_res = high_res.cuda()

        super_res, _, _, _ = model(low_res)

        loss = criterion(super_res, high_res)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        # scheduler.step()

        n_iter += 1

        if n_iter % log_interval == 0:
            print('epoch [{}/{}], iteration [{}], loss: {:.5f}'.format(epoch + 1,
                max_epochs, n_iter, loss.item()))

            writer.add_scalar('data/loss', loss.item(), n_iter)

        if n_iter % viz_interval == 0:
            
            grid_image = torch.cat(((0.5 * (high_res + 1)).cpu(), (0.5 * (super_res + 1)).cpu() ))
            
            progress_images = vutils.make_grid(grid_image, normalize=True)
            writer.add_image('resolutions', progress_images, n_iter)


    if ((epoch + 1) % save_interval == 0) and (epoch + 1) > 5:
        checkpoint_file = os.path.join(expt_folder, 'states', training_set,'srresnet_%d.pkl' % (epoch + 1))
        torch.save(model.state_dict(), checkpoint_file)


    berror = 0
    verror = 0
    viters = 0
    for low_res, high_res in validloader:

        low_res = low_res.cuda()
        high_res = high_res.cuda()

        super_res, _, _, _ = model(low_res)
        verror += utils.avg_psnr(super_res, high_res)

        n_samples = low_res.shape[0]
        baseline_res = torch.stack([bicubic_transform(low_res.detach().cpu()[i, :, :, :]) for i in range(n_samples)]).cuda()
        berror += utils.avg_psnr((2 * baseline_res) - 1, high_res)

        viters += 1

    writer.add_scalar('data/super_psnr', verror / viters, n_iter)
    writer.add_scalar('data/bicubic_psnr', berror / viters, n_iter)

        
writer.close()

