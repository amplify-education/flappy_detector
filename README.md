# Flappy Detector
Lambda project for detecting flappy resources in AWS.

## Getting Started
### Prerequisites
Flappy Detector requires the following to be installed:
```text
python >= 3.8
tox >= 2.9.1
docker
serverless
npm
nodejs
```

### Running Tests
`tox` will automatically execute linters as well as the unit tests.

To see all the available options, run `tox -l`.

### Deployment
-   `npm install` The Serverless Framework project depends on a few plugins defined in `package.json`. 
    This will install them.

-   `sls deploy -s <stage>` Stage is typically the environment such as `ci` or the account like `prod`

-   `sls invoke -s <stage> -f hello` The sample generated function is named `hello`. The `sls invoke` command can be 
    used to test lambdas directly before invoking them via a AWS event (API Gateway, SNS, Cloudwatch, etc)
