import boto3
import sys
from botocore.exceptions import ClientError
import logging
import sys
import uuid
import re
import argparse

### creating a log file for the code 
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s  %(name)s  %(levelname)s: %(message)s')

file_handler = logging.FileHandler('restoreS3AsyncObjectRestore.log')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)


s3 = boto3.client("s3")
sts = boto3.client("sts")

##start of the getting and configuring S3 event configuration
# method to determine accountID 
def getAccountID():
    account_id = sts.get_caller_identity()
    return account_id['Account'], account_id['Arn'].split(':')[5].split('/')[1]

#global variable
ownerAccountId = getAccountID()[0]
userName = getAccountID()[1]

#creating a policy with a unique name by randomizing using uuid lib
def createRestorePolicy(bucketName, Events):
    policy = {
                    'Id': f"Added S3 event notification for restore - {bucketName} - {str(uuid.uuid4())}",
                    'TopicArn': SNSArn,
                    'Events': Events,
                }
    return policy


# putting S3 restore configuration for the bucket. Policy is generated from addOrUpdateS3Event method
def putEventConfiguration(bucketName, policy):
    try:
        s3.put_bucket_notification_configuration(
            Bucket= bucketName,
             ExpectedBucketOwner=ownerAccountId,
            NotificationConfiguration=policy
        )
    except s3.exceptions.NoSuchBucket:
        logger.error (f"Bucket '{bucketName}' does not exists. Exiting ...")
        sys.exit()
    except ClientError as error:
        if error.response['Error']['Code'] == 'InvalidArgument':
            logger.error(f"Check SNS Access Policy Permissions. You may not get notification if it is not set correctly")
        else:
            logger.error(f"Unexpected error: %s" % error)
    else:
        logger.error(f"Something wrong with SNS configuration...Please make sure SNS topic is configured correctly")
        sys.exit(1)

# getting the current S3 event configuration for the bucket. It could be null or have some S3 events
# such as put, copy or even restore. This method returns the list of configured s3 events on the bucket 
# and S3 bucket event configuration.
def getEventConfiguration(bucketName, key):
    configList = []
    #getting the latest configuration data
    try:
        configuration = s3.get_bucket_notification_configuration(
        Bucket=bucketName,
        ExpectedBucketOwner=ownerAccountId
        )
    except s3.exceptions.NoSuchBucket:
        logger.error (f"Bucket '{bucketName}' does not exists. Exiting out ...")
        sys.exit()
    # if no s3 restore events are found, no update to the configDict
    if len(configuration) == 0:
        logger.info(f"No S3 event configuration is set for a bucket {bucketName}. Addding a configuration for s3:ObjectRestore:Post,s3:ObjectRestore:Completed for the restore process")
        configList = []  
    else:  
        #checking to see if restore initiation and completion already set
        # deleting the value for the ResponseMetadata key from the get_bucket_notification_configuration query
        del configuration['ResponseMetadata']
        # one configuration can have mutliple values, checking both scenarios.
        for val in configuration.values():
            if len(val) > 1:
                for v in val:
                    configList.extend(v['Events'])
            else:   
                configList.extend(val[0]['Events'])
    return configList,configuration


#This method adds or append S3 event configuration of the bucket with  's3:ObjectRestore:Post', 's3:ObjectRestore:Completed'
#scenario #1: If no S3 event is configured, it adds the s3 events for S3 restore initiation and completed
#Scenario #2: Check if either of 's3:ObjectRestore:Post' or/and 's3:ObjectRestore:Completed' are not configured on the bucket. Create a list of missing S3 restore events
    #2a. if Topic Configuration exists, append the existing Topic Configuration with the S3 retore event from the list and keep rest of the S3 event policy unchanged
    #2b. if Topic Configuration does not exist, add new topic Configuration with the S3 retore event from the list and keep rest of the S3 event policy unchanged.   
        
def addOrUpdateS3Event(bucketName,key):
    eventsList = ['s3:ObjectRestore:Post', 's3:ObjectRestore:Completed']
    restoreList= []
    cfList, config = getEventConfiguration(bucketName, key)
    #If no S3 event is set, it adds the s3 events for S3 restore initiation and completed
    if cfList == []:
        # create a S3 event restore policy for initiation and complete
        s3EventPolicy = createRestorePolicy(bucketName, eventsList)
        eventDt= {'TopicConfigurations': [s3EventPolicy]}
        #configure S3 events for restoring object with SNS topic
        putEventConfiguration(bucketName, eventDt)
        logger.info(f"No S3 event Configuration found. Added a new restore s3 event policy for the bucket {bucketName}")
    else:
        #Check if either of 's3:ObjectRestore:Post' or/and 's3:ObjectRestore:Completed' are not configured on the bucket 
        # create a restoreList of the restore S3 event(s) not configured
        for event in eventsList:
            if event not in cfList:
                restoreList.append(event)
        #if restoreList is not empty, that means restore s3 events needs to configured either or initiation or completed or both.    
        if restoreList != []:
            s3EventPolicy = createRestorePolicy(bucketName, restoreList)
            eventDt= {'TopicConfigurations': [s3EventPolicy]}
            #TopicConfiguration already exists then append the existing TopicConfiguraton with the S3 restore event(s) recorded in the  restoreList
            if 'TopicConfigurations' in config.keys():
                config['TopicConfigurations'].extend(eventDt['TopicConfigurations'])
                putEventConfiguration(bucketName, config)
                logger.info(f"Appended Existing Topic Configuration for S3 restore event policy for the bucket {bucketName}")
            else:
                #TopicConfiguration does not exist then added TopicConfiguraton with the S3 restore event(s) recorded in the  restoreList
                config.update(eventDt)
                putEventConfiguration(bucketName,config)
                logger.info(f"Added Topic Configuration for S3 restore event policy for the bucket {bucketName}")
## end of the getting and configuring S3 event configuration 

## start of restoring object
#If you were able to get the object, then this code does nothing. the user should be able to get the object without any issue.
# if the object status is invalid, then check the object metadata with the head call to the object metadata
def getObject(bucketName, key):
    try:
        s3.get_object(
            Bucket = bucketName,
            Key = key)
    # if user accidently add wrong bucket name, it get Access Denied error
    except ClientError as error:
        #if bucket does not exists it throw Access Denied error
        if error.response['Error']['Code'] == 'AccessDenied':
            logger.error (f"PLease ensure bucket - {bucketName} or key - {key} belongs to the account - {ownerAccountId}")
            sys.exit()
        #check to see if key provided exists, else exit.
        elif error.response['Error']['Code'] == 'NoSuchKey':
            logger.error (f"{key} does not exists in the {bucketName}")
            sys.exit()
        #object may be in Async storage or restore is in progress
        elif error.response['Error']['Code'] =='InvalidObjectState':
            logger.info (f"the object '{key}' in the bucket '{bucketName}' is in Invalid Object state, ... checking object status")
            headObject(bucketName,key)
    else:
        logger.info (f"the object '{key}' in the bucket '{bucketName}' is not in an S3 Intelligent async tier or Glacier storage class")


#Retriving object metadata to check its archive status.
# need to add a policy with to use HEAD, you must have READ access to the object.
def headObject(bucketName, key):
    try:
        response = s3.head_object(
        Bucket = bucketName,
        Key = key)
    #Checking if bucket exists. If not, exiting out
    except s3.exceptions.NoSuchBucket:
        logger.error (f"Bucket '{bucketName}' does not exists. Exiting out ...")
        sys.exit()
    #else checking archive status
    #find the status of x-amz-restore. If x-amz-restore does not exist, run RestoreObject status call
    restoreStatus = response['ResponseMetadata']['HTTPHeaders'].get('x-amz-restore')
    # if restore status is true, restore is in progress   
    if restoreStatus == 'ongoing-request="true"':
        logger.info(f"A restore of an Object '{key}' is already in progress")
    # if object archive status is "DEEP_ARCHIVE_ACCESS" or "ARCHIVE_ACCESS" and StorageClass is Intelligent-Tiering
    # and 'x-amz-restore" does not exists then restore object.
    elif response['StorageClass'] == 'INTELLIGENT_TIERING':
        if (response['ArchiveStatus'] == "DEEP_ARCHIVE_ACCESS" or response['ArchiveStatus'] == "ARCHIVE_ACCESS") and restoreStatus is None:
            #execute restore for the S3 INT Async tiers
            executeRestoreS3INT(bucketName, key,response['ArchiveStatus'])  
    #Restoring Object from Glacier Flexible Retrievable/ Glacier Deep Archive storage classes
    # if object archive status is "DEEP_ARCHIVE_ACCESS" or "ARCHIVE_ACCESS"
    # then 'x-amz-restore" does not exists then restore object. 
    elif (response['StorageClass'] == "DEEP_ARCHIVE" or response['StorageClass'] == "GLACIER") and restoreStatus is None:
        #No.of args required to restore object from Glacier are 5. 
        #fifth argument is optional
        #if no. of args are 4, setting expirationDays = 7 as a default value.
        if expirationDays is None :
            expirationinDays = 1
            logger.info(f"Object is in Glacier storage class, since you have not provided the expiration days, setting it '{expirationinDays}' days")
        else:
            expirationinDays = expirationDays
        #execute restore for the Glacier Storage class
        executeRestoreGlacier(bucketName, key,response['StorageClass'],expirationinDays)
    else:
        logger.info(f"An object '{key}' is already restored")

###Start of restoring object
#To use this operation, you must have permissions to perform the s3:RestoreObject action for object in S3 INT AA/DAA
def executeRestoreS3INT(bucketName, key,restoreStatus): 
    #adding/appending/updating S3 event configuration for the S3 bucket for restoring object.
    addOrUpdateS3Event(bucketName,key)
    if restoreStatus == "DEEP_ARCHIVE_ACCESS":
            logger.info(f"Restoring an object {key} from the 'DEEP_ARCHIVE_ACCESS' tier to S3 INT FA. It will be back into Amazon S3 within 12 hours")
    else:
        logger.info(f"Restoring an object {key} from the 'ARCHIVE_ACCESS' tier to S3 INT FA.It will be back into Amazon S3 INT FA within 3-5 hours")
    #restoring an object from the S3 INT Archive/Deep Archive Access.
    try:
        s3.restore_object(
            Bucket=bucketName,
            Key=key,
            RestoreRequest={})
    except s3.exceptions.ObjectAlreadyInActiveTierError:
        logger.error(f"Restore action is not allowed against this storage tier {restoreStatus}.")

#To use this operation, you must have permissions to perform the s3:RestoreObject action for object in S3 INT AA/DAA
def executeRestoreGlacier(bucketName, key,restoreStatus, expirationDays): 
    #adding/appending/updating S3 event configuration for the S3 bucket for restoring object.
    addOrUpdateS3Event(bucketName,key)
    if restoreStatus == "DEEP_ARCHIVE":
            logger.info(f"Restoring an object {key} from the 'DEEP_ARCHIVE' Class to S3 STD. It will be back into Amazon S3 STD within 12 hours for '{expirationDays}' days")
    else:
        logger.info(f"Restoring an object {key} from the 'GLACIER' class to S3 STD. It will be back into Amazon S3 STD within 3-5 hours for '{expirationDays}' days")
#restoring an object from the S3 Glacier Glacier Flexible Retrievable/Deep Archive Access.
    try:
        s3.restore_object(
            Bucket=bucketName,
            Key=key,
            RestoreRequest={"Days": expirationDays, "GlacierJobParameters":{"Tier":"Standard" }})
    except s3.exceptions.ObjectAlreadyInActiveTierError:
        logger.error(f"Restore action is not allowed against this storage tier {restoreStatus}.")

### end of restoring S3 object


def main():
    global bucketName
    global key 
    global SNSArn 
    global expirationDays

    parser= argparse.ArgumentParser(description='Restoring objects from the S3 Async Storage')
    parser.add_argument("-b", "--BucketName", type=str, metavar="", required=True, help="Bucket Name" )
    parser.add_argument("-k", "--Key", type=str, metavar="", required=True, help="prefix/key or key" )
    parser.add_argument("-s", "--SNSArn", type=str, metavar="", required=True, help="SNS Arn" )
    parser.add_argument("-e", "--ExpirationDays", type=int, metavar="", help="Expiration in Days is optional" )
    args = parser.parse_args()
    bucketName= args.BucketName
    key = args.Key
    SNSArn = args.SNSArn
    expirationDays = args.ExpirationDays
    if not re.search('arn:aws:sns:[a-z0-9\-]+:[a-z0-9\-]+:[a-z0-9\-]*', SNSArn):
            logger.error (f"Please check if your SNS Arn format. SNS arn format must be - arn:aws:sns:[a-z0-9\-]+:[a-z0-9\-]+:[a-z0-9\-]*. For example: arn:aws:sns:us-east-1:123456789123:restore")
            logger.info (f"exiting ....")
            sys.exit(1) 
    
    # getObject calls headObject which calls executeRestoreS3INT or executeRestoreGlacier depending the object restore status
    getObject(bucketName,key)
    
if __name__ == "__main__":
    main()
    
    
