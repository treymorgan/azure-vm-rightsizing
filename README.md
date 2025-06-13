# Azure VM Right-Sizing Tool

A Python-based tool for identifying cost optimization opportunities in Azure by analyzing VM utilization and providing right-sizing recommendations.

## Overview

This tool helps organizations optimize their Azure cloud costs by:

- Analyzing CPU utilization across all Azure VMs in a subscription
- Identifying underutilized VMs based on configurable thresholds
- Providing actionable recommendations for right-sizing or deallocation
- Reporting on stopped/deallocated VMs that may be candidates for deletion

## Features

- **Comprehensive Analysis**: Examines all VMs in a subscription
- **Power State Awareness**: Categorizes VMs by running and stopped states
- **Customizable Thresholds**: Configurable CPU utilization thresholds for determining underutilization
- **Detailed Reporting**: Provides actionable recommendations with specific metrics
- **Easy Authentication**: Uses Azure's DefaultAzureCredential for simplified authentication
- **Interactive Subscription Selection**: Choose which subscription to analyze when you have multiple

## Prerequisites

- Python 3.6+
- Azure subscription with VM resources
- Permissions to read Azure Monitor metrics

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/treymorgan/azure-vm-rightsizing.git
   cd azure-vm-rightsizing
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Authenticate with Azure:
   ```bash
   az login
   ```

2. Run the script:
   ```bash
   python vm_rightsizing.py
   ```

3. If you have multiple subscriptions, you'll be prompted to select one.

## Sample Output

```
VM Status Summary:
- Running VMs: 12
- Stopped/Deallocated VMs: 5
- Total VMs: 17

VM Right-Sizing Recommendations:
+-------------+------------------+----------+--------------+-------------+-----------------------------------+
| VM Name     | Resource Group   | Location | VM Size      | Avg CPU (%) | Recommendation                    |
+-------------+------------------+----------+--------------+-------------+-----------------------------------+
| webserver01 | production-rg    | eastus   | Standard_D4s | 12.45       | Consider downsizing or deallocating |
| appserver03 | production-rg    | eastus   | Standard_D8s | 8.32        | Consider downsizing or deallocating |
| dbserver02  | production-rg    | eastus   | Standard_E8s | 22.67       | Consider downsizing or deallocating |
+-------------+------------------+----------+--------------+-------------+-----------------------------------+
```

## Customization

You can adjust the following parameters in the script:

- `CPU_THRESHOLD`: The percentage threshold for considering a VM underutilized (default: 30%)
- `DAYS_TO_ANALYZE`: The number of days of metrics to analyze (default: 7)

## Advanced Integration

For ongoing optimization, consider:

- Schedule the script with Azure Automation or GitHub Actions
- Store results in Azure Storage or Log Analytics
- Connect with Azure Advisor for deeper context
- Integrate with your cloud governance workflows

## Troubleshooting

If you encounter issues:

- Ensure you're authenticated with `az login`
- Check that your account has permissions to access VM and metrics data
- Verify that VMs have been running long enough to generate metrics
- Ensure Azure Monitor is properly configured

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
