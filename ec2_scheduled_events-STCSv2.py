"""
author: adrilon
2019 July 10 Wednesday
version: 2.0

This script will pull all AWS scheduled EC2 events in STCS account and notify it's respective application owner group.

Note:
    Before running this script, be sure to set stcs as your default profile in your STS credential retrieval tool

"""

import boto3
import requests
from botocore.exceptions import ClientError
from time import sleep
import logging

# Setup Logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s')

file_handler = logging.FileHandler('ScheduledEvents_summary.log')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)


# Function to get all AWS scheduled events with the following filtered values
def get_ec2_scheduled_events(client):

    ec2_events = client.describe_instance_status(
        Filters=[
            {
                'Name': 'event.code',
                'Values': ['instance-stop','instance-reboot','system-reboot', 'system-maintenance', 'instance-retirement']
            }
        ]
    )

    return ec2_events

# Function to display events in MS teams (connected via webhook connector)
def send_message_msteams(chat_channel, instance_region, ownerID, instance_id, instanceName, customerPrefix, recipient, event_description, deadline):

    try:
        uri = chat_channel
        body = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "ff0000",
            "title": "AWS Scheduled Report: ",
            "text": "EC2 Scheduled report - STCS",
            "sections": [{
                "activityTitle": "Instance Description",
                "facts" : [
                    {
                        "name": "AWS ACcount: ",
                        "value": ownerID
                    },
                    {
                        "name": "Region: ",
                        "value": instance_region
                    },
                    {
                        "name": "Instance ID: ",
                        "value": instance_id
                    },
                    {
                        "name": "Name: ",
                        "value": instanceName
                    },
                    {
                        "name": "Alias: ",
                        "value": customerPrefix
                    },
                    {
                        "name": "Owner: ",
                        "value": recipient
                    }
                ],
                "markdown": False
              },
              {
              "activityTitle": "Event Details: ",
                "facts" : [
                    {
                        "name": "Description: ",
                        "value": event_description
                    },
                    {
                        "name": "Deadline: ",
                        "value": deadline
                    }
                ],
                "markdown": False
            }]
        }
        response = requests.post(uri, json=body, headers={'Content-Type':'application/json'})
    except Exception as e:
        raise e



def main():
    if __name__ == '__main__':

        # Setup temp client to get list of available regions
        ec2_conn = boto3.client('ec2', 'us-east-1')
        ses_client = boto3.client('ses')
        s3_client = boto3.client('s3')
        s3_resource = boto3.resource('s3')

        sleepTime = 3
        counter = 0

        # Getting list of available regions for user
        regions = [region['RegionName'] for region in \
                   (ec2_conn.describe_regions())['Regions']]
        # Counter helps to work with API RequestLimitExceed errors
        while (counter < 5):
            try:
                # Checking each region available for user
                for region in regions:
                    ec2_conn = boto3.client('ec2', region_name=region)
                    if 'ap-east-1' not in region:
                            scheduled_events = get_ec2_scheduled_events(ec2_conn)
                            for instances in scheduled_events['InstanceStatuses']:
                                if "Completed" not in instances['Events'][0]['Description'] and \
                                "Canceled" not in instances['Events'][0]['Description']:
                                    # Initialization of variables
                                    report = {}
                                    instanceName = ''
                                    customerPrefix = ''
                                    owner = ''
                                    service = ''
                                    product = ''
                                    instance_region = ''
                                    ownerID = ''
                                    recipient = ''

                                    # Describe instance details
                                    ec2_instance_details = ec2_conn.describe_instances(
                                        Filters=[
                                            {
                                                'Name': 'instance-id',
                                                'Values': [instances['InstanceId']]
                                            }
                                        ]
                                    )
                                    # Variables assignment acquired through describe instances
                                    event_description = instances['Events'][0]['Description']
                                    instance_id = instances['InstanceId']
                                    deadline = str(instances['Events'][0]['NotBefore'])
                                    instance_region = ec2_instance_details['Reservations'][0]['Instances'][0]['Placement']['AvailabilityZone']
                                    ownerID = ec2_instance_details['Reservations'][0]['Instances'][0]['NetworkInterfaces'][0]['OwnerId']
                                    report.update({'Region': instance_region, 'AWS Account': ownerID})

                                    # Acquire instance tags information (Name, Customer Prefix, Service, Product, Owner)
                                    for tag in ec2_instance_details['Reservations'][0]['Instances'][0]['Tags']:
                                        report.update({'Description': event_description, 'InstanceID': instance_id, 'Deadline': deadline})
                                        if tag['Key'] == 'Name':
                                            instanceName = tag['Value']
                                            report.update({tag['Key']: instanceName})
                                        elif tag['Key'] == 'customerPrefix':
                                            customerPrefix = tag['Value']
                                            report.update({tag['Key']: customerPrefix})
                                        elif tag['Key'] == 'Service':
                                            service = tag['Value']
                                            report.update({tag['Key']: service})
                                        elif tag['Key'] == 'Product':
                                            product = tag['Value']
                                            report.update({tag['Key']: product})
                                        elif tag['Key'] == 'Owner':
                                            owner = tag['Value']
                                            report.update({'Owner': owner})

                                    # Product list identifying server application roles
                                    lawson = ['pubapp', 'ion', 'iso', 'lmrk', 'lsf', 'cb', 'depm', 'gfc', 'eam', 'mscm']
                                    m3 = ['m3', 'ft', 'glt', 'm3base', 'Mongoose', 'olap', 'plm', 'clm']
                                    db_service = ['db-mssql', 'db-postgres']
                                    identical_product = ['bi', 'ies', 'mingle']

                                    # Filter to identify support teams DL (Filtered through Product, Service and Owner tags)
                                    if 'Product' in report:
                                        # Filter for products that are identical for M3 and Lawson app servers, checked through Owner tag specified
                                        if report['Product'] in identical_product:
                                            if 'm3' or 'crea' in report['Owner']:
                                                recipient = 'DL-TEAM-CLOUD-OPS-CMS-M3-SYSADM-MNL@infor.com'
                                            elif 'tarek' or 'tiger' in report['Owner']:
                                                recipient = 'DL-TEAM-LE-TIGER@infor.com'
                                        #Filter server's product based on PRODUCT tags
                                        elif report['Product'] in lawson:
                                            recipient = 'DL-TEAM-LE-TIGER@infor.com'
                                        elif report['Product'] in m3:
                                            recipient = 'DL-TEAM-CLOUD-OPS-CMS-M3-SYSADM-MNL@infor.com'
                                        elif report['Product'] == 'infra':
                                            recipient = 'DL-TEAM-CLOUD-OPS-SYSADMINS@infor.com'
                                        elif report['Product'] == 'WFM':
                                            recipient = 'DLG-NA-ICSOnCall-WFM-CRM@Infor.com'
                                        elif 'db' in report['Product']:
                                            recipient = 'DL-TEAM-CLOUD-OPS-MONITORING-DBA@infor.com'
                                        else:
                                            recipient = 'DL-TEAM-CLOUD-OPS-SYSADMINS@infor.com'
                                    elif 'Product' not in report:
                                        if report['Service'] in db_service:
                                            recipient = 'DL-TEAM-CLOUD-OPS-MONITORING-DBA@infor.com'
                                        elif 'm3' or 'crea' in report['Owner']:
                                            recipient = 'DL-TEAM-CLOUD-OPS-CMS-M3-SYSADM-MNL@infor.com'
                                        elif 'tarek' or 'tiger' in report['Owner']:
                                            recipient = 'DL-TEAM-LE-TIGER@infor.com'
                                        else:
                                            recipient = 'DL-TEAM-CLOUD-OPS-SYSADMINS@infor.com'
                                    else:
                                        recipient = 'DL-TEAM-CLOUD-OPS-SYSADMINS@infor.com'

                                    report.update({'Recipient' : recipient})

                                    # S3 bucket upload for events tracker and logs
                                    object_summary = report['InstanceID'] + "_" + report['Description']
                                    try:
                                        response = s3_client.get_object(
                                            Bucket='infor-sthybrid-infrashared-us-east-1',
                                            Key='ssm/aws-scheduled-events/{object_name}'.format(object_name=object_summary)
                                        )
                                        print("The Event {} is already sent to {} and has been uploaded in S3 bucket.".format(object_summary, report['Recipient']))
                                        logger.info("The Event {} is already sent to {} and has been uploaded in S3 bucket.".format(object_summary, report['Recipient']))

                                    except ClientError as ex:
                                        if ex.response['Error']['Code'] == 'NoSuchKey':
                                            obj = s3_resource.Object('infor-sthybrid-infrashared-us-east-1','ssm/aws-scheduled-events/{object_name}'\
                                                                     .format(object_name=object_summary))
                                            object_content = str(report)
                                            obj.put(Body=object_content)
                                            print("Event uploaded - {} and has been sent to {}".format(object_summary, report['Recipient']))
                                            logger.info("Event uploaded - {} and has been sent to {}".format(object_summary, report['Recipient']))

                                            # Sending email
                                            response = ses_client.send_email(
                                                Source='noreply-cloudnotification@infor.com',
                                                Destination={
                                                    'ToAddresses': [
                                                        '{}'.format(report['Recipient']),

                                                    ]
                                                },
                                                Message={
                                                    'Subject': {
                                                        'Data': "AWS Scheduled Event Notification",
                                                        'Charset': 'UTF-8'
                                                    },
                                                    'Body': {
                                                        'Html': {
                                                            'Charset': 'UTF-8',
                                                            'Data': "<br>Hi Team,"
                                                                    "<br><br>We have received an AWS scheduled event alert for the below customer. "\
                                                                    "Kindly complete the required action based on the event description prior the indicated deadline to avoid unexpected outage.<br><br>"
                                                                    '<table border="1"><tr><th>AWS Account</th><th>Region</th><th>Name</th><th>Instance ID</th><th>Description</th><th>Deadline</th></tr>\
                                                                    <tr>\
                                                                    <td>' + ownerID + '</td>\
                                                                    <td>' + instance_region + '</td>\
                                                                    <td>' + instanceName + '</td>\
                                                                    <td>' + instance_id + '</td>\
                                                                    <td>' + event_description + '</td>\
                                                                    <td>' + deadline + ' UTC+8</td>\
                                                                    </tr>\
                                                                    </table>'
                                                                    "<br><br>For degraded hardware event, kindly perform an AWS instance stop/start via AWS console or use CSP Admin function SGW - Instance Stop/Start. "
                                                                    "<br><br><b> -- Please do not reply to this email -- </b>"
                    
                                                        }
                                                    }
                                                }
                                            )
                                            chat_channel = "https://outlook.office.com/webhook/842cbb15-9b3d-4c21-8195-c0e5920fb36e@457d5685-0467-4d05-b23b-8f817adda47c/IncomingWebhook/19d39580cfae4cd59a3cdbf2546bbf4d/4aacf2c9-44ca-48cf-bf6f-8475b6000a8e"
                                            send_message_msteams(chat_channel, instance_region, ownerID, instance_id, instanceName, customerPrefix, recipient, event_description, deadline)
            except Exception as e:
                print(e)
                sleep(sleepTime**counter)
                counter = counter + 1

            counter = 5

if __name__ == '__main__':
    main()
