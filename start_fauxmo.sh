#!/bin/bash

# Kill any existing fauxmo processes
pkill -f fauxmo

# Start fauxmo with proper permissions
sudo fauxmo -c fauxmo_config.json -vvv
