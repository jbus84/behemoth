#!/bin/bash
LOG="/private/tmp/claude-501/-Users-danielfisher-repositories-behemoth/29a5a524-217e-44f6-af71-80efb5e9b004/tasks/bperck8ku.output"
until grep -q "done symbols=5 months=96" "$LOG" 2>/dev/null; do
  sleep 30
done
echo "$(date): BATCH 2 COMPLETE - starting batch 3" >> /tmp/batch3_trigger.log
cd /Users/danielfisher/repositories/behemoth
/tmp/download_crosses.sh "CHFJPY,NZDUSD,EURNZD,GBPNZD,AUDNZD" /Users/danielfisher/Desktop/tick 2>&1 | tee /tmp/download_batch3.log
echo "$(date): BATCH 3 DONE" >> /tmp/batch3_trigger.log
