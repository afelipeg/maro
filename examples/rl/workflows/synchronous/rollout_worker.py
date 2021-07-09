# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import sys
from os import environ
from os.path import dirname, realpath

from maro.rl.learning.synchronous import rollout_worker_node


workflow_dir = dirname(dirname(realpath(__file__)))  # template directory
if workflow_dir not in sys.path:
    sys.path.insert(0, workflow_dir)

from agent_wrapper import get_agent_wrapper
from general import config, get_env_wrapper, log_dir


if __name__ == "__main__":
    rollout_worker_node(
        config["sync"]["rollout_group"],
        int(environ["WORKERID"]),
        get_env_wrapper(),
        get_agent_wrapper(),
        proxy_kwargs={"redis_address": (config["redis"]["host"], config["redis"]["port"])},
        log_dir=log_dir
    )
