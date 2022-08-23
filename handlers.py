from abc import ABC, abstractclassmethod
from datetime import datetime, timedelta
from traceback import format_exc
from google.oauth2.service_account import Credentials
from google.cloud.monitoring_v3 import MetricServiceClient, TimeInterval, ListTimeSeriesRequest
from googleapiclient import discovery
from time import time
from azure.mgmt.compute import ComputeManagementClient
from azure.identity import ClientSecretCredential
from requests import get

class Handler(ABC):

    @abstractclassmethod
    def transform(account):
        pass

    def handle(func):

        def wrapped(account, logger):
            account_name = account['ent_name']
            try:
                logger.info(f"Fetching VMs KPIs for '{account_name}'.")
                return func(account)
            except Exception as e:
                logger.error(f"Error for account '{account_name}': {str(e)}\n{format_exc()}")

        return wrapped

class GCP(Handler):

    @Handler.handle
    def transform(account):
        timestamp = int(str(datetime.now().timestamp()).split('.')[0])
        creds = account["credentials"]
        project_name = f"projects/{creds['project_id']}"
        credentials = Credentials.from_service_account_info(creds)
        client = MetricServiceClient(credentials=credentials)
        service = discovery.build('compute', 'v1', credentials=credentials)
        request = service.instances().aggregatedList(project=creds["project_id"])
        instances = []
        while request is not None:
            response = request.execute()
            for _, instances_scoped_list in response['items'].items():
                if "instances" in instances_scoped_list:
                    instances.extend(instances_scoped_list["instances"])
            request = service.instances().aggregatedList_next(previous_request=request, previous_response=response)
        filtered_instances = []
        for instance in instances:
            filtered_instance = {
                "timestamp": timestamp,
                "ent_name": account["ent_name"],
                "provider": account["provider"],
                "name": instance["name"]
            }
            for metric_type in account["metrics"]["gcp"]:
                metric_name = metric_type.split('/')[-1]
                if account["template"][metric_name]["enable"]:
                    filtered_instance[metric_name] = "NaN"
                    metric_value = GCP._get_metric_value(client, project_name, metric_type, instance["name"])
                    if metric_value is not None:
                        filtered_instance[metric_name] = metric_value
            filtered_instances.append(filtered_instance)
        return list(map(lambda x: dict(sorted(x.items(), key=lambda y: y[0])), filtered_instances))

    def _get_metric_value(client, project_name, metric_type, instance_name):
        try:
            now = time()
            seconds = int(now)
            nanos = int((now - seconds) * 10 ** 9)
            return client.list_time_series(
                request={
                    "name": project_name,
                    "filter": f'metric.type = "{metric_type}" AND metric.labels.instance_name = "{instance_name}"',
                    "interval": TimeInterval(
                        {
                            "end_time": {"seconds": seconds, "nanos": nanos},
                            "start_time": {"seconds": (seconds - 1200), "nanos": nanos},
                        }
                    ),
                    "view": ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )._response.time_series[-1].points[-1].value.double_value
        except:
            pass

class Azure(Handler):

    class AzureMonitorClient:

        def __init__(self, credentials):
            self.root_url = "https://management.azure.com"
            self.credentials = credentials
            self.token = self._get_token()

        def _get_token(self):
            token = self.credentials.get_token(f"{self.root_url}/.default").token
            return f"Bearer {token}"

        def _request(self, request_func, *args, **kwargs):
            params = kwargs.get("params", {})
            params["api-version"] = "2018-01-01"
            return request_func(headers={"Authorization": self.token}, *args, **kwargs)

        def list_metric_definitions(self, ressource_id):
            url = f"{self.root_url}{ressource_id}/providers/Microsoft.Insights/metricDefinitions"
            return self._request(get, url).json()

        def get_metrics_values(self, ressource_id, metrics):
            end = datetime.now()
            start = end - timedelta(minutes=122)
            timespan = f"{start.isoformat()}/{end.isoformat()}"
            url = f"{self.root_url}{ressource_id}/providers/Microsoft.Insights/metrics"
            return self._request(get, url, params={"metricnames": metrics, "timespan": timespan, "aggregation": "Average"}).json()

    @Handler.handle
    def transform(account):
        timestamp = int(str(datetime.now().timestamp()).split('.')[0])
        creds = account["credentials"]
        credentials = ClientSecretCredential(client_id=creds["client_id"], client_secret=creds["client_secret"], tenant_id=creds["tenant_id"])
        compute_client = ComputeManagementClient(credentials, creds["subscription_id"])
        monitor_client = Azure.AzureMonitorClient(credentials)
        vm_list = list(compute_client.virtual_machines.list_all())
        instances = []
        for vm in vm_list:
            instance = {
                "timestamp": timestamp,
                "ent_name": account["ent_name"],
                "provider": account["provider"],
                "name": vm.name
            }
            filtered_metrics = list(filter(lambda metric: account['template'][metric]['enable'], account["metrics"]["azure"]))
            instance |= Azure._get_metrics_values(monitor_client, vm.id, filtered_metrics)
            instances.append(instance)
        return list(map(lambda x: dict(sorted(x.items(), key=lambda y: y[0])), instances))

    def _get_metrics_values(client, vm_id, metrics):
        result = {}
        metric_string = ','.join(metrics)
        metrics = client.get_metrics_values(vm_id, metric_string)["value"]
        for metric in metrics:
            metric_name = metric['name']['value']
            result[metric_name] = "NaN"
            try:
                data = metric["timeseries"][0]["data"]
                metrics = list(map(lambda d: d["average"], filter(lambda d: "average" in d, data)))
                result[metric_name] = sum(metrics) / len(metrics)
            except:
                pass
        return result