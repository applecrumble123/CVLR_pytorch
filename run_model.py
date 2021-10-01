import numpy as np
import pandas as pd
import os
import re
from cv2 import cv2
import shutil
import random
import torchvision.io
from torch.utils.data import DataLoader, Dataset
from typing import Optional, Callable, Tuple, Any
from resnet_3D_50 import ResNet, block
from torch.nn import functional as F
import torchvision.transforms.functional
import pickle


from PIL import Image
from torchvision import transforms


import torch
import torch.nn as nn
from tqdm import tqdm
from torch.utils.tensorboard import SummaryWriter

import warnings
warnings.filterwarnings('ignore')

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print("There are {} GPUs available".format(torch.cuda.device_count()))

""" ----------------- Folder path -------------------- """
ROOT_FOLDER = '/Users/johnathontoh/Desktop/CVLR'
DATA_FOLDER = os.path.join(ROOT_FOLDER, 'data')
DATA_LIST_FOLDER = os.path.join(ROOT_FOLDER, 'ucfTrainTestlist')
CLASS_LIST_TEXT_FILE = os.path.join(DATA_LIST_FOLDER, 'classInd.txt')

""" ------------------- Get train, test and val dataset ------------------ """
# class number label, class name
class_labelling = []

# class name
class_name_labelling = []

# class_num label
class_num_labelling = []

with open(CLASS_LIST_TEXT_FILE) as f:
    # read the lines
    lines = f.readlines()
    for line in lines:
        # split by '\n' and a space
        new_line_split = line.split()
        class_labelling.append(new_line_split)

# get a list of class name
for idx, name in class_labelling:
    class_name_labelling.append(name)
    class_num_labelling.append(idx)



""" --- training set --- """
train_class = []
train_videos = []
train_num_label = []

""" --- test set --- """
test_class = []
test_videos = []
test_num_label = []

def split_test_train(name, class_array, videos_array, num_label_array):
    # run through the 'ucfTrainTestlist' folder to get the text file
    for text_file in os.listdir(DATA_LIST_FOLDER):
        # if the 'train' word is in the file name
        if name in text_file:
            #print(text_file)
            # get the text_file path
            file_path = os.path.join(DATA_LIST_FOLDER, text_file)
            # open the text file
            with open(file_path) as f:
                # read the lines
                lines = f.readlines()
                for line in lines:
                    # replace '/' with a spacing
                    new_line = line.replace('/', ' ')
                    # print(new_line)
                    # split each line in the text file to get the class, video name and number label
                    split_line = new_line.split()
                    #print(split_line)
                    # length of line is 3 (consist of class, video name, number label)
                    if len(split_line) == 3:
                        # append to the class array
                        class_array.append(split_line[0])
                        # append to the video array
                        videos_array.append(os.path.join(ROOT_FOLDER,'UCF-101',split_line[0],split_line[1]))
                        # append to the num_label array
                        num_label_array.append((split_line[2]))
                    # no number label in the test folder so need to append to it
                    # length of line is 2
                    else:
                        # each 'class_num_label' has a number label and a class label i.e ['1', 'ApplyEyeMakeup']
                        for class_num_label in (class_labelling):
                            #print(class_num_label)
                            # if the element in split line is the same as the class label
                            if split_line[0] == class_num_label[1]:
                                # append the number label to the split line list
                                split_line.append(class_num_label[0])
                                # append to the class array
                                class_array.append(split_line[0])
                                # append to the video array
                                videos_array.append(os.path.join(ROOT_FOLDER, 'UCF-101', split_line[0], split_line[1]))
                                # append to the num_label array
                                num_label_array.append((split_line[2]))



split_test_train(name='train', class_array=train_class, videos_array=train_videos, num_label_array=train_num_label)
split_test_train(name='test', class_array=test_class, videos_array=test_videos, num_label_array=test_num_label)


""" Load the entire video instead of the 16 frames"""
""" --------- Create Dataset class ----------- """

class VideoDataset(Dataset):

    def __init__(self, class_labels, vid, transform = None):
        super().__init__()
        self.class_labels = class_labels
        self.vid = vid
        self.transform = transform

    def __getitem__(self, index: int):

        # get one video and its label
        vid_path, class_num_label = self.vid[index], self.class_labels[index]

        # can also use torch vision
        video, audio, info = torchvision.io.read_video(filename=vid_path)
        #print(video.size())

        total_vid_frames = video.size()[0]
        #print(total_vid_frames)




        tensor_clip = torch.reshape(video,
                                      [video.size()[0],
                                       video.size()[3],
                                       video.size()[1],
                                       video.size()[2]])




        if self.transform is not None:

            # do transformation as PIL images on the entire clip using the TrainTransform class
            # returns a list of transformed PIL images
            transformed_clip = self.transform(tensor_clip)



            # convert the entire clip list to tensor
            # convert the PIL images to tensor then stack
            tensor_clip = torch.stack([transforms.functional.to_tensor(pic) for pic in transformed_clip])


            tensor_clip = torch.reshape(tensor_clip,
                                          [tensor_clip.size()[0],
                                           tensor_clip.size()[3],
                                           tensor_clip.size()[1],
                                           tensor_clip.size()[2]])





        # returns a tuple of clip_1, clip_2 and the its label
        return tensor_clip, class_num_label

    # get the length of total dataset
    def __len__(self):
        return len(self.vid)

"""
dataset = VideoDataset(class_labels=train_num_label, vid=train_videos)
print(dataset.__len__())
first_data = dataset[3]
#print(first_data)
"""

""" --------- Create Transform class ----------- """
# only do resizing because there is no transformation needed for downstream tasks
class CVLRTransform(object):

    def __init__(self):

        data_transforms = [
            transforms.RandomResizedCrop(size=224, scale=(0.3, 1), ratio=(0.5, 2)),
            #transforms.ToTensor()

        ]
        self.train_transform = transforms.Compose(data_transforms)

    # sample refers to one clip
    def __call__(self, sample):

        # call the train_transform
        transform = self.train_transform

        # get the list of transformed frames
        transformed_clip = []

        for frame in sample:
            # takes in the frames as numpy array and convert to PIL image to do the transformation
            #im_pil = Image.fromarray(frame)
            im_pil = transforms.ToPILImage()(frame).convert("RGB")
            # do the transformation which will then convert to tensors
            transf_img = transform(im_pil)

            # append it to the list, which will be called by the dataset class in the '__getitem__' function
            transformed_clip.append(transf_img)

        return transformed_clip



""" ----- Train Dataloader ----- """
train_transformed_dataset = VideoDataset(class_labels=train_num_label, vid=train_videos, transform=CVLRTransform())

# batch size 1 to get the features of one video in the training set
train_dataloader = DataLoader(train_transformed_dataset,
                              batch_size=1,
                              shuffle=True,
                              # uncomment when using server
                              #num_workers=3
                              )


""" ----- Test Dataloader ----- """
test_transformed_dataset = VideoDataset(class_labels=test_num_label, vid=test_videos, transform=CVLRTransform())

# batch size 1 to get the features of one video in the test set
test_dataloader = DataLoader(test_transformed_dataset,
                              batch_size=1,
                              shuffle=True,
                              # uncomment when using server
                              #num_workers=3
                              )




class ResNet_3D_50(ResNet):
    def __init__(self):
        super(ResNet_3D_50, self).__init__(block, layers=[3,4,6,3], image_channels=3)
        #self.fc = nn.Linear(512 * 4, num_classes)

    # get the features from the CNN layers
    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)


        h = self.avgpool(x)
        h = h.squeeze()
        return h

"""
def test():
    model = ResNet_3D_50()
    x = torch.randn(10, 3, 3, 224, 224)
    # get the representations and the projections
    output = model(x)
    print(output.size())

#test()
"""
#model = ResNet_3D_50()
model = ResNet_3D_50()
model = nn.DataParallel(model, device_ids=list(range(torch.cuda.device_count())))
model.eval()
state_dict = torch.load('/Users/johnathontoh/Desktop/CVLR/saved_model/epoch_10_model.pt', map_location=torch.device('cpu'))

model.load_state_dict(state_dict)
model = model.to(device)
"""
print("Model's state_dict:")
for param_tensor in model.state_dict():
    print(param_tensor, "\t", model.state_dict()[param_tensor].size())
"""
#print(list(model.modules()))


#new_model = nn.Sequential(*list(model.modules())[:-2])
#print(new_model)

"""
for layer in new_model:
    print(layer)
"""

# freeze all the layers in the resnet model
for param in model.parameters():
    param.requires_grad = False
    #print(param)


x_train = []
y_train = []

"""
len(sample_batched) = 2 (video frames, class labels)
"""

for i_batch, sample_batched in enumerate(train_dataloader):
    img = sample_batched[0]
    img = torch.reshape(img, [img.size()[0], img.size()[3], img.size()[1], img.size()[2], img.size()[4]])
    outputs = model(img).to(device)
    x_train.extend(outputs)
    y_train.extend(sample_batched[1])
    #break
    #print(outputs.size())

train_features_path = os.path.join(ROOT_FOLDER, 'train_features')

with open('x_train.pkl', 'wb') as f:
    pickle.dump(x_train, f)

with open('y_train.pkl', 'wb') as f:
    pickle.dump(y_train, f)

print(x_train)
print(y_train)


"""
for i_batch, sample_batched in enumerate(train_dataloader):
    #print(type(sample_batched))
    print(len(sample_batched))
    print(sample_batched[0].size())
    print(sample_batched[1].size())
    print(sample_batched[2])

    #print(sample_batched[0].size())
    img = sample_batched[0]

    img = torch.reshape(img, [img.size()[0], img.size()[3], img.size()[1], img.size()[2], img.size()[4]])

    print(type(img))
    outputs = new_model(img).to(device)
    print(len(outputs))
    break
"""

















