from __future__ import print_function
from __future__ import division
import sys
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import torchvision
from torchvision import datasets, models, transforms
from torch.utils.data.dataset import random_split
from shufflenet import ShuffleNet
import torch.utils.data


import time
import copy
print("PyTorch Version: ", torch.__version__)
print("Torchvision Version: ", torchvision.__version__)

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
# Top level data directory. Here we assume the format of the directory conforms
# to the ImageFolder structure
data_dir = "/video/clef/LifeCLEF/PlantCLEF2019/train/data"
data_dir_web = "/video/clef/LifeCLEF/PlantCLEF2017/web/data"


# Models to choose from [resnet, alexnet, vgg, squeezenet, densenet, inception]
model_name = "densenet"

# Number of classes in the dataset
num_classes = 8500

# Batch size for training (change depending on how much memory you have)
batch_size = 48
# Number of epochs to train for
num_epochs = 100

# Flag for feature extracting. When False, we finetune the whole model,
#   when True we only update the reshaped layer params
feature_extract = False


def make_weights_for_balanced_classes(images, nclasses):
    count = [0] * nclasses
    for item in images:
        count[item[1]] += 1
    weight_per_class = [0.] * nclasses
    N = float(sum(count))
    for i in range(nclasses):
        weight_per_class[i] = N/float(count[i])
    weight = [0] * len(images)
    for idx, val in enumerate(images):
        weight[idx] = weight_per_class[val[1]]
    return weight


def my_collate(batch):
    batch = list(filter(lambda x: x is not None, batch))
    return torch.utils.data.dataloader.default_collate(batch)


class MyImageFolder(datasets.ImageFolder):
    __init__ = datasets.ImageFolder.__init__
    def __getitem__(self, index):
        try:
            return super(MyImageFolder, self).__getitem__(index)
        except Exception as e:
            print(e) # Return None here for my_collate


def train_model(model, dataloaders, criterion, optimizer, num_epochs=25,
                is_inception=False, save_model_every=10):
    global model_name
    since = time.time()
    val_acc_history = []
    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0
    for epoch in range(num_epochs):
        i = 0
        print('Epoch {}/{}'.format(epoch, num_epochs - 1))
        print('-' * 10)
        # Each epoch has a training and validation phase
        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()
            else:
                model.eval()
            running_loss = 0.0
            running_corrects = 0
            running_samples = 0
            for inputs, labels in dataloaders[phase]:
                i += 1
                inputs = inputs.to(device)
                labels = labels.to(device)
                optimizer.zero_grad()
                with torch.set_grad_enabled(phase == 'train'):
                    if is_inception and phase == 'train':
                        outputs, aux_outputs = model(inputs)
                        loss1 = criterion(outputs, labels)
                        loss2 = criterion(aux_outputs, labels)
                        loss = loss1 + 0.4*loss2
                    else:
                        outputs = model(inputs)
                        loss = criterion(outputs, labels)
                    _, preds = torch.max(outputs, 1)

                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                running_loss += loss.item()*inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)
                running_samples += np.prod(list(labels.data.size()))
                if (i % 1000) == 0:
                    print("batch: ", i, " - loss: ",
                          running_loss/running_samples,
                          "- acc: ",
                          running_corrects.cpu().numpy()/running_samples)

            epoch_loss = running_loss / len(dataloaders[phase].dataset)
            epoch_acc = running_corrects.double() / len(
                dataloaders[phase].dataset
            )

            print('{} loss: {:.4f} Acc: {:.4f}'.format(
                phase, epoch_loss, epoch_acc)
            )
            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())
            if phase == 'val':
                val_acc_history.append(epoch_acc)
        if epoch % save_model_every == 0:
            torch.save(model_ft.state_dict(),
                       model_name + "_dict_" + str(epoch) + ".pth")
            torch.save(val_acc_history,
                       model_name + "_" + str(epoch) + ".hist")
        print()
    time_elapsed = time.time() - since
    print("Training complete in {:.0f}m {:.0f}s".format(
        time_elapsed // 60, time_elapsed % 60))
    print('Best val Acc: {:.4f}'.format(best_acc))
    model.load_state_dict(best_model_wts)
    return model, val_acc_history


def set_parameter_requires_grad(model, feature_extracting):
    if feature_extracting:
        for param in model.parameters():
            param.requires_grad = False


def initialize_model(model_name, num_classes,
                     feature_extract, use_pretrained=True):
    # Initialize these variables which will be set in this if statement.
    # Each of these variables is model specific.
    model_ft = None
    input_size = 0

    if model_name == "resnet":
        """ Resnet18
        """
        model_ft = models.resnet18(pretrained=use_pretrained)
        set_parameter_requires_grad(model_ft, feature_extract)
        num_ftrs = model_ft.fc.in_features
        model_ft.fc = nn.Linear(num_ftrs, num_classes)
        input_size = 224

    elif model_name == "alexnet":
        """ Alexnet
        """
        model_ft = models.alexnet(pretrained=use_pretrained)
        set_parameter_requires_grad(model_ft, feature_extract)
        num_ftrs = model_ft.classifier[6].in_features
        model_ft.classifier[6] = nn.Linear(num_ftrs, num_classes)
        input_size = 224

    elif model_name == "vgg":
        """ VGG11_bn
        """
        model_ft = models.vgg11_bn(pretrained=use_pretrained)
        set_parameter_requires_grad(model_ft, feature_extract)
        num_ftrs = model_ft.classifier[6].in_features
        model_ft.classifier[6] = nn.Linear(num_ftrs, num_classes)
        input_size = 224

    elif model_name == "squeezenet":
        """ Squeezenet
        """
        model_ft = models.squeezenet1_0(pretrained=use_pretrained)
        set_parameter_requires_grad(model_ft, feature_extract)
        model_ft.classifier[1] = nn.Conv2d(512, num_classes,
                                           kernel_size=(1, 1), stride=(1, 1))
        model_ft.num_classes = num_classes
        input_size = 224

    elif model_name == "densenet":
        """ Densenet
        """
        model_ft = models.densenet121(pretrained=use_pretrained)
        set_parameter_requires_grad(model_ft, feature_extract)
        num_ftrs = model_ft.classifier.in_features
        model_ft.classifier = nn.Linear(num_ftrs, num_classes)
        input_size = 224
    elif model_name == "shufflenet":
        model_ft = ShuffleNet(groups=3, num_classes=num_classes, in_channels=3)
        input_size = 224

    elif model_name == "inception":
        """ Inception v3
        Be careful, expects (299,299) sized images and has auxiliary output
        """
        model_ft = models.inception_v3(pretrained=use_pretrained)
        set_parameter_requires_grad(model_ft, feature_extract)
        # Handle the auxilary net
        num_ftrs = model_ft.AuxLogits.fc.in_features
        model_ft.AuxLogits.fc = nn.Linear(num_ftrs, num_classes)
        # Handle the primary net
        num_ftrs = model_ft.fc.in_features
        model_ft.fc = nn.Linear(num_ftrs, num_classes)
        input_size = 299

    else:
        print("Invalid model name, exiting...")
        exit()

    return model_ft, input_size


if __name__ == '__main__':
    model_ft, input_size = initialize_model(model_name, num_classes,
                                    feature_extract, use_pretrained=False)
    if (len(sys.argv) >= 2):
        try:
            model_dict = model_ft.state_dict()
            pretrained_dict = torch.load(sys.argv[1])
            pretrained_dict = {k: v for k, v in pretrained_dict.items() if k in model_dict}
            model_ft.load_state_dict(pretrained_dict)
        except:
            pretrained_dict = torch.load(sys.argv[1])
            model_ft = models.densenet201(pretrained=False)
            set_parameter_requires_grad(model_ft, feature_extract)
            num_ftrs = model_ft.classifier.in_features
            model_ft.classifier = nn.Linear(num_ftrs, 10000)
            model_dict = model_ft.state_dict()
            pretrained_dict = torch.load(sys.argv[1])
            pretrained_dict = {k: v for k, v in pretrained_dict.items() if k in model_dict}
            model_ft.load_state_dict(pretrained_dict)
            num_ftrs = model_ft.classifier.in_features
            model_ft.classifier = nn.Linear(num_ftrs, num_classes)
    print(model_ft)

    # Data augmentation and normalization for training
    # Just normalization for validation
    data_transforms = {
        'train': transforms.Compose([
            transforms.RandomResizedCrop(input_size),
            transforms.RandomRotation((0, 360)),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ]),
        'val': transforms.Compose([
            transforms.Resize(input_size),
            transforms.CenterCrop(input_size),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ]),
    }

    print("Initializing Datasets and Dataloaders...")

    # Create training and validation datasets
    image_datasets = {x: MyImageFolder(data_dir, data_transforms[x])
                      for x in ['train']}
    weights = make_weights_for_balanced_classes(
        image_datasets['train'].imgs,
        len(image_datasets['train'].classes))

    weights = torch.DoubleTensor(weights)
    sampler = torch.utils.data.sampler.WeightedRandomSampler(
        weights, len(weights))

    '''
    image_datasets['val'] = MyImageFolder(data_dir_web, data_transforms['val'])
    '''
    train_dataset_len = len(image_datasets['train'])
    _, image_datasets['val'] = random_split(image_datasets['train'],[int(train_dataset_len*0.8), train_dataset_len - int(train_dataset_len*0.8)])
    '''
    '''
    # Create training and validation dataloaders
    dataloaders_dict = {'train': torch.utils.data.DataLoader(
        image_datasets['train'],
        batch_size=batch_size,
        num_workers=4, collate_fn=my_collate,
        sampler=sampler),
        'val': torch.utils.data.DataLoader(
                image_datasets['val'],
                batch_size=batch_size,
                num_workers=4, collate_fn=my_collate
                )
        }

    # Initialize the model for this run

    # Print the model we just instantiated

    # Send the model to GPU
    model_ft = model_ft.to(device)

    # Gather the parameters to be optimized/updated in this run. If we are
    #  finetuning we will be updating all parameters. However, if we are
    #  doing feature extract method, we will only update the parameters
    #  that we have just initialized, i.e. the parameters with requires_grad
    #  is True.
    params_to_update = model_ft.parameters()
    print("Params to learn:")
    if feature_extract:
        params_to_update = []
        for name, param in model_ft.named_parameters():
            if param.requires_grad:
                params_to_update.append(param)
                print("\t", name)
    else:
        for name, param in model_ft.named_parameters():
            if param.requires_grad:
                print("\t", name)

    # Observe that all parameters are being optimized
    optimizer_ft = optim.SGD(params_to_update, lr=0.001, momentum=0.9)


    # Setup the loss fxn
    criterion = nn.CrossEntropyLoss()

    # Train and evaluate
    model_ft, hist = train_model(model_ft, dataloaders_dict,
                                criterion, optimizer_ft,
                                num_epochs=num_epochs,
                                is_inception=(model_name == "inception")
                                )
    torch.save(model_ft.state_dict(), model_name + ".pth")
    torch.save(hist, model_name + ".hist")
