# Info
This is the implementation of the tests to be used by the [test environment](../../test/README.md).

* The test framework used is **pytest**;
* Implemented tests can vary from:
    * Unit;
    * Integration;
    * E2E (end-to-end);

## Running tests locally
1 - Create venv
```sh
python3 -m venv .venv
```
```sh
source .venv/bin/activate
```
2 - Install requirements
```sh
pip install --no-cache-dir -r requirements.txt
```
3 - Run tests
```sh
python run_tests.py --test-path integration/
```

## Running tests on container
1- Build container image
```sh
docker build -t gprofiler-test .
```
2 - Start test container in attached mode
```sh
docker run --rm -t --network host --env-file .env gprofiler-test python run_tests.py --test-path integration/
```