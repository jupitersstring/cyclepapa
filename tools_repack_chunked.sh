#!/bin/bash
# Chunked repack for a repository whose loose objects (6.3 GB of re-committed
# CSV books) exceed the free disk a full `git gc` needs for its temp pack.
# Loose objects are packed in batches grouped by PATH (versions of the same
# file delta against each other), and the packed loose copies are pruned after
# every batch, so disk is recovered progressively instead of needed up front.
# Usage: bash tools_repack_chunked.sh [batch_mb=400]
set -u
cd "$(dirname "$0")"
BATCH_MB=${1:-400}
export GIT_DIR=.git
# loose objects: sha -> size
declare -A LOOSE
while IFS= read -r p; do
  sha="$(basename "$(dirname "$p")")$(basename "$p")"
  LOOSE[$sha]=$(stat -c %s "$p")
done < <(find .git/objects/?? -type f 2>/dev/null)
echo "loose objects: ${#LOOSE[@]}"
# reachable objects with paths, blobs/trees grouped by path; unreached loose get pruned at the end
git rev-list --objects --all | awk '{print ($2==""?"~":$2), $1}' | sort > /tmp/repack_objs.txt
batch=0; acc=0; : > /tmp/repack_batch.txt
flush() {
  if [ -s /tmp/repack_batch.txt ]; then
    batch=$((batch+1))
    git pack-objects --delta-base-offset --window=40 --depth=50 -q .git/objects/pack/pack < /tmp/repack_batch.txt > /dev/null \
      && git prune-packed -q && echo "batch $batch packed ($((acc/1048576)) MB loose) | free $(df -h / | tail -1 | awk '{print $4}')"
    : > /tmp/repack_batch.txt; acc=0
  fi
}
while read -r path sha; do
  sz=${LOOSE[$sha]:-}
  [ -z "$sz" ] && continue
  echo "$sha $path" >> /tmp/repack_batch.txt
  acc=$((acc+sz))
  if [ "$acc" -ge $((BATCH_MB*1048576)) ]; then flush; fi
done < /tmp/repack_objs.txt
flush
git prune --expire=now 2>/dev/null
echo "done: packs $(ls .git/objects/pack/*.pack | wc -l) | loose left $(find .git/objects/?? -type f | wc -l) | .git $(du -sh .git | cut -f1) | free $(df -h / | tail -1 | awk '{print $4}')"
