#!/bin/bash

SERVICE="z13gui.service"

# Check if the service is active (running)
if systemctl --user is-active --quiet "$SERVICE"; then
    echo "🔴 $SERVICE is currently running. Stopping it..."
    systemctl --user stop "$SERVICE"
    
    # Verify it stopped
    if ! systemctl --user is-active --quiet "$SERVICE"; then
        echo "✅ $SERVICE has been stopped successfully."
    else
        echo "❌ Failed to stop $SERVICE."
        exit 1
    fi
else
    echo "🟢 $SERVICE is not running. Starting it..."
    systemctl --user start "$SERVICE"
    
    # Verify it started
    if systemctl --user is-active --quiet "$SERVICE"; then
        echo "✅ $SERVICE has been started successfully."
    else
        echo "❌ Failed to start $SERVICE."
        exit 1
    fi
fi
