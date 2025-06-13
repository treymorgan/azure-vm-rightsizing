#!/usr/bin/env python3
"""
Azure VM Right-Sizing Recommendations Script

This script analyzes Azure VM CPU utilization and provides right-sizing recommendations
for underutilized VMs to optimize cost.
"""

import sys
import logging
from datetime import datetime, timedelta
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.resource import SubscriptionClient
from azure.core.exceptions import HttpResponseError, ClientAuthenticationError
from tabulate import tabulate

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Configuration
CPU_THRESHOLD = 30  # CPU percentage threshold for considering a VM underutilized
DAYS_TO_ANALYZE = 7  # Number of days of metrics to analyze


def authenticate_azure():
    """
    Authenticate with Azure using DefaultAzureCredential.
    Returns the credential object or exits if authentication fails.
    """
    try:
        logger.info("Authenticating with Azure...")
        credential = DefaultAzureCredential()
        # Test the credential with a small operation
        subscription_client = SubscriptionClient(credential)
        subscription_client.subscriptions.list(top=1)
        logger.info("Authentication successful")
        return credential
    except ClientAuthenticationError as e:
        logger.error(f"Authentication failed: {str(e)}")
        logger.error("Please ensure you are logged in (az login) or have appropriate environment variables set")
        sys.exit(1)


def get_subscription(credential, subscription_id=None):
    """
    Get the subscription to use. If subscription_id is provided, use that.
    Otherwise, list available subscriptions and let the user choose.
    """
    subscription_client = SubscriptionClient(credential)
    
    try:
        subscriptions = list(subscription_client.subscriptions.list())
        
        if not subscriptions:
            logger.error("No subscriptions found for the authenticated account")
            sys.exit(1)
            
        if subscription_id:
            # Use the provided subscription ID
            for sub in subscriptions:
                if sub.subscription_id == subscription_id:
                    logger.info(f"Using subscription: {sub.display_name} ({sub.subscription_id})")
                    return sub.subscription_id
            logger.error(f"Subscription ID {subscription_id} not found")
            sys.exit(1)
        elif len(subscriptions) == 1:
            # If there's only one subscription, use that
            subscription = subscriptions[0]
            logger.info(f"Using the only available subscription: {subscription.display_name} ({subscription.subscription_id})")
            return subscription.subscription_id
        else:
            # Let the user choose from available subscriptions
            print("\nAvailable subscriptions:")
            for i, sub in enumerate(subscriptions):
                print(f"{i+1}. {sub.display_name} ({sub.subscription_id})")
            
            choice = input("\nSelect a subscription (number): ")
            try:
                index = int(choice) - 1
                if 0 <= index < len(subscriptions):
                    subscription = subscriptions[index]
                    logger.info(f"Selected subscription: {subscription.display_name} ({subscription.subscription_id})")
                    return subscription.subscription_id
                else:
                    logger.error("Invalid selection")
                    sys.exit(1)
            except ValueError:
                logger.error("Invalid input, please enter a number")
                sys.exit(1)
    except HttpResponseError as e:
        logger.error(f"Error listing subscriptions: {str(e)}")
        sys.exit(1)


def get_virtual_machines(credential, subscription_id):
    """
    Retrieve all virtual machines in the subscription.
    Returns a list of VMs with their details, including power state.
    """
    try:
        logger.info("Retrieving virtual machines...")
        compute_client = ComputeManagementClient(credential, subscription_id)
        vms = compute_client.virtual_machines.list_all()
        
        vm_list = []
        running_vms = []
        stopped_vms = []
        
        for vm in vms:
            resource_group = vm.id.split("/")[4]
            
            # Get VM instance view to check power state
            instance_view = compute_client.virtual_machines.instance_view(
                resource_group_name=resource_group,
                vm_name=vm.name
            )
            
            # Extract power state from status
            power_state = "unknown"
            for status in instance_view.statuses:
                if status.code.startswith("PowerState/"):
                    power_state = status.code.split("/")[1].lower()
                    break
            
            vm_info = {
                "name": vm.name,
                "resource_group": resource_group,
                "location": vm.location,
                "vm_size": vm.hardware_profile.vm_size if hasattr(vm.hardware_profile, 'vm_size') else "Unknown",
                "id": vm.id,
                "power_state": power_state
            }
            
            vm_list.append(vm_info)
            
            if power_state == "running":
                running_vms.append(vm.name)
            elif power_state in ["stopped", "deallocated"]:
                stopped_vms.append(vm.name)
        
        logger.info(f"Found {len(vm_list)} virtual machines total")
        logger.info(f"Running VMs: {len(running_vms)} - {', '.join(running_vms) if running_vms else 'None'}")
        logger.info(f"Stopped/Deallocated VMs: {len(stopped_vms)} - {', '.join(stopped_vms) if stopped_vms else 'None'}")
        
        return vm_list
    except HttpResponseError as e:
        logger.error(f"Error retrieving virtual machines: {str(e)}")
        sys.exit(1)


def get_cpu_utilization(monitor_client, vm, subscription_id, start_time, end_time):
    """
    Get CPU utilization metrics for a VM over the specified time period.
    """
    try:
        logger.debug(f"Retrieving CPU metrics for VM: {vm['name']}")
        resource_uri = f"/subscriptions/{subscription_id}/resourceGroups/{vm['resource_group']}/providers/Microsoft.Compute/virtualMachines/{vm['name']}"
        
        metrics_data = monitor_client.metrics.list(
            resource_uri=resource_uri,
            timespan=f"{start_time.isoformat()}Z/{end_time.isoformat()}Z",
            interval='PT1H',
            metricnames='Percentage CPU',
            aggregation='Average'
        )
        
        cpu_values = []
        for item in metrics_data.value:
            for timeseries in item.timeseries:
                for data in timeseries.data:
                    if data.average is not None:
                        cpu_values.append(data.average)
        
        logger.info(f"VM {vm['name']} CPU values: {cpu_values if cpu_values else 'No CPU data available'}")
        return cpu_values
    except HttpResponseError as e:
        logger.warning(f"Error retrieving metrics for VM {vm['name']}: {str(e)}")
        return []


def is_underutilized(cpu_data, threshold=CPU_THRESHOLD):
    """
    Determine if a VM is underutilized based on CPU metrics.
    Returns a tuple of (is_underutilized, average_cpu).
    """
    if not cpu_data:
        return False, 0.0
    
    avg_cpu = sum(cpu_data) / len(cpu_data)
    return avg_cpu < threshold, avg_cpu


def generate_recommendations(vm_list, credential, subscription_id):
    """
    Generate right-sizing recommendations based on CPU utilization.
    Only analyzes running VMs.
    """
    logger.info("Analyzing VM utilization and generating recommendations...")
    
    monitor_client = MonitorManagementClient(credential, subscription_id)
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=DAYS_TO_ANALYZE)
    
    recommendations = []
    vms_without_data = []
    running_vms = [vm for vm in vm_list if vm.get("power_state") == "running"]
    stopped_vms = [vm for vm in vm_list if vm.get("power_state") in ["stopped", "deallocated"]]
    
    if not running_vms:
        logger.warning("No running VMs found to analyze")
        return recommendations, vms_without_data, running_vms, stopped_vms
    
    for count, vm in enumerate(running_vms, 1):
        logger.info(f"Processing running VM {count}/{len(running_vms)}: {vm['name']}")
        
        cpu_data = get_cpu_utilization(monitor_client, vm, subscription_id, start_time, end_time)
        
        if not cpu_data:
            vms_without_data.append(vm['name'])
            continue
            
        underutilized, avg_cpu = is_underutilized(cpu_data)
        
        if underutilized:
            recommendations.append({
                "VM Name": vm['name'],
                "Resource Group": vm['resource_group'],
                "Location": vm['location'],
                "VM Size": vm['vm_size'],
                "Avg CPU (%)": round(avg_cpu, 2),
                "Recommendation": "Consider downsizing or deallocating"
            })
    
    if vms_without_data:
        logger.warning(f"No CPU metrics data available for {len(vms_without_data)} running VMs: {', '.join(vms_without_data)}")
        logger.warning("These VMs might not be collecting metrics. Check Azure Monitor diagnostics settings.")
    
    logger.info(f"Found {len(recommendations)} VMs that could be optimized")
    return recommendations, vms_without_data, running_vms, stopped_vms


def main():
    """
    Main function to run the VM right-sizing analysis.
    """
    logger.info("Starting Azure VM right-sizing analysis")
    
    # Get authentication credential
    credential = authenticate_azure()
    
    # Get subscription ID (can be replaced with a parameter)
    subscription_id = get_subscription(credential)
    
    # Get VMs
    vm_list = get_virtual_machines(credential, subscription_id)
    
    if not vm_list:
        logger.warning("No virtual machines found in the subscription")
        return
    
    # Generate recommendations
    recommendations, vms_without_data, running_vms, stopped_vms = generate_recommendations(vm_list, credential, subscription_id)
    
    # Output VM status summary
    print("\nVM Status Summary:")
    print(f"- Running VMs: {len(running_vms)}")
    print(f"- Stopped/Deallocated VMs: {len(stopped_vms)}")
    print(f"- Total VMs: {len(vm_list)}")
    
    # Output recommendations
    if recommendations:
        print("\nVM Right-Sizing Recommendations:")
        print(tabulate(recommendations, headers="keys", tablefmt="grid"))
        
        # You could also save to a file
        # with open('vm_rightsizing_recommendations.csv', 'w') as f:
        #     f.write(','.join(recommendations[0].keys()) + '\n')
        #     for rec in recommendations:
        #         f.write(','.join(str(v) for v in rec.values()) + '\n')
    elif len(running_vms) == 0:
        print("\nNo running VMs found in the subscription.")
        print("To generate right-sizing recommendations, start your VMs so metrics can be collected.")
    elif vms_without_data and len(vms_without_data) == len(running_vms):
        print("\nNo optimization recommendations could be generated.")
        print(f"No CPU metrics data available for any of the running VMs: {', '.join(vms_without_data)}")
        print("\nRecommendations:")
        print("1. Ensure Azure Monitor diagnostics settings are properly configured")
        print("2. Check if the Azure Monitor agent is installed and running on the VMs")
        print("3. Wait at least 24 hours after configuring monitoring for metrics to be collected")
    elif vms_without_data:
        print("\nPartial data available for analysis.")
        print(f"No CPU metrics data available for {len(vms_without_data)} of {len(running_vms)} running VMs:")
        print(', '.join(vms_without_data))
        print("\nAll analyzed VMs are properly utilized (above the CPU threshold).")
    else:
        print("\nNo optimization recommendations found. All running VMs are properly utilized.")
        
    # Print stopped VM details as potential cost saving opportunity
    if stopped_vms:
        print("\nStopped/Deallocated VMs (potential cost optimization):")
        stopped_vm_details = [{
            "VM Name": vm['name'],
            "Resource Group": vm['resource_group'],
            "Location": vm['location'],
            "VM Size": vm['vm_size'],
            "Status": vm['power_state'].capitalize(),
            "Recommendation": "Consider deleting if no longer needed"
        } for vm in stopped_vms]
        print(tabulate(stopped_vm_details, headers="keys", tablefmt="grid"))


if __name__ == "__main__":
    main()
