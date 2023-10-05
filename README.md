###

# py_vw_carnet

## Description

py_vw_carnet provides access to VW carnet, including session management,
and providing API access.

## Installation

```
python3 -m pip install  git+https://github.com/rhhayward/py_vw_carnet.git@master
```

## Usage

Example:

```
from vw_carnet import CarNet

import os

u = os.environ['VW_USERNAME']
p = os.environ['VW_PASSWORD']

cn = CarNet(u,p)

carStatus = cn.getCarStatus()
for carId in carStatus.keys():
    car = carStatus[carId]
    print("carId={}".format(carId))
    print(" +++ currentMileage={}".format(car['data']['currentMileage']))
    print(" +++ nextMaintenanceMilestone={}".format(car['data']['nextMaintenanceMilestone']))
    print(" +++ timestamp={}".format(car['data']['timestamp']))
    print(" +++ exteriorStatus={}".format(car['data']['exteriorStatus']))
    print(" +++ powerStatus={}".format(car['data']['powerStatus']))
    print(" +++ lastParkedLocation={}".format(car['data']['lastParkedLocation']))
    print(" +++ clampState={}".format(car['data']['clampState']))
    print(" +++ clampStateTimestamp={}".format(car['data']['clampStateTimestamp']))
    print(" +++ platform={}".format(car['data']['platform']))
    print(" +++ lockStatus={}".format(car['data']['lockStatus']))

```
