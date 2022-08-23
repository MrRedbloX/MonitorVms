# MonitorVMs
## Description
A script which fetches various metrics of VM instances of different Cloud providers and send those metrics to a Kafka cluster.
## Supported providers:
- GCP
- Azure
## Input file
You will need to add a file named **config.json**.  
Check the file *ressources/config_template.json* to see how to build it.
## Using templates
You can use the default templates or create new ones with different metrics enabled.
## Account permissions
Service account for each providers requires different permissions.
Check the file *resources/account_permissions.txt* to see those permissions.
## Requirements
First install Python with the version in the file *runtime.txt*.  
Make sure you install pip package manager with it.  
Set up the virtual environnement and install all the requirements:
```
python -m pip install venv
python -m venv venv
./venv/Scrips/activate
pip install -r requirements.txt
```
## Execution
### Main script
Run the following command:
```
python main.py
```
A message will appear: *Press any key to stop...*.
### Consume messages
Run the following command (if you do this in another terminal you will need to run the activate script again):
```
python test_consumer.py
```
You should see the messages appear.
### Debug
All the application logs are available in the **debug.log** file.
