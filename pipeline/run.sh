#!/bin/bash

python detect.py \
--video clips/entry.mp4 \
--store-id STORE_BLR_001 \
--camera-id CAM_ENTRY_01 \
--camera-type ENTRY \
--output events.jsonl