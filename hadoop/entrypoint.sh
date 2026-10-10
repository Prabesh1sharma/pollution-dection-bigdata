#!/usr/bin/env bash
set -e

# Run Hadoop configuration generator from environment variables
/opt/envtoconf.py --destination "${HADOOP_CONF_DIR:-/opt/hadoop/etc/hadoop}"

# Format NameNode if directory does not exist
if [ -n "$ENSURE_NAMENODE_DIR" ]; then
  CLUSTERID_OPTS=""
  if [ -n "$ENSURE_NAMENODE_CLUSTERID" ]; then
    CLUSTERID_OPTS="-clusterid $ENSURE_NAMENODE_CLUSTERID"
  fi
  if [ ! -d "$ENSURE_NAMENODE_DIR" ]; then
    /opt/hadoop/bin/hdfs namenode -format -force $CLUSTERID_OPTS
  fi
fi

# Clear datanode data directory if namenode was reformatted
if [ "$1" = "hdfs" ] && [ "$2" = "datanode" ]; then
  rm -rf /tmp/hdfs/data/*
fi

exec "$@"
