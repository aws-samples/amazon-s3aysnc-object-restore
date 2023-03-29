# amazon-s3aysnc-object-restore



## Getting started


Here is how the code works to restore an object from the S3 object from S3 Async Storage -  S3 Glacier Flexible Retrieval, S3 Glacier Deep Archive, Archive Access, and Deep Archive Access.

**Implementation Overview**:

**Customer makes a GetObject call**

- If HTTP 403 InvalidObjectState error is returned, make HeadObject call to check Archive state

    **For S3 INT AA/DAA** - 

        No. of arguments required - Bucket name, Prefix/key and SNSArn

            If x-amz-archive-access == DEEP_ARCHIVE_ACCESS or ARCHIVE_ACCESS, check x-amz-restore

            If x-amz-restore does not exist, send RestoreObject call

            Else If x-amz-restore == true, a restore is already in progress

            Else If x-amz-restore == false, object is already restored


    **For S3 Glacier GFR/GDA** - 

        No. of arguments required - Bucket name, Prefix/key, SNSArn and expirationDays 
        ExpirationDays is an optional argument. If not provided, it is set to 30 days. 

            If storage class == DEEP_ARCHIVE or GLACIER, check x-amz-restore

            If x-amz-restore does not exist, send RestoreObject call

            Else If x-amz-restore == true, a restore is already in progress
            
            Else If x-amz-restore == false, object is already restored 

The code also checks if any other S3 events is configured on a bucket. 
        
- First getting the current S3 event configuration for the bucket. It could be null or have some S3 events configured such as put, copy or even restore
-     
- Adding or appending S3 event configuration of the bucket with 's3:ObjectRestore:Post', 's3:ObjectRestore:Completed' if it is not configured


**scenario #1**: If no S3 event is configured, it adds the s3 events for S3 restore initiation and completed.

**Scenario #2**: Check if either of 's3:ObjectRestore:Post' or/and 's3:ObjectRestore:Completed' are not configured on the bucket.
Create a list of missing S3 restore events:
        
1. if Topic Configuration exists, append the existing Topic Configuration with the S3 restore event from the list and keep the rest of the S3 event policy unchanged.

2. if Topic Configuration does not exist, add new topic Configuration with the S3 restore event from the list and keep the rest of the S3 event policy unchanged.   
     

_**Here is the Command to run the code for restoring an object from the async classes or tiers is  - 
restoreS3AsyncObjectRestore.py bucketname prefix/key SNSArn expirationDays . Ex: restoreS3Object.py s3bucket nothingtoseehere/nothing.csv0030part00 arn:aws:sns:us-east-1:123456789123:restore 2. Expiration days parameter is optional. If you don't provide Expiration days and object happens to be in S3 Glacier classes, the code will restore the object from the Glacier class for 30 days.**_





