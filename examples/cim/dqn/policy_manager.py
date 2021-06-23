# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import os
import sys

from maro.rl import LocalPolicyManager, MultiNodePolicyManager, MultiProcessPolicyManager

dqn_path = os.path.dirname(os.path.realpath(__file__))  # DQN directory
cim_path = os.path.dirname(dqn_path)  # CIM example directory
sys.path.insert(0, cim_path)
sys.path.insert(0, dqn_path)
from general import AGENT_IDS, NUM_POLICY_TRAINERS, config, log_dir
from policy import get_independent_policy_for_training


policies = [get_independent_policy_for_training(i) for i in AGENT_IDS]
if config["policy_manager"]["policy_training_mode"] == "single-process":
    policy_manager = LocalPolicyManager(policies, log_dir=log_dir)
elif config["policy_manager"]["policy_training_mode"] == "multi-process":
    policy_manager = MultiProcessPolicyManager(
        policies,
        {id_: f"TRAINER.{id_ % NUM_POLICY_TRAINERS}" for id_ in AGENT_IDS}, # policy-trainer mapping
        {i: get_independent_policy_for_training for i in AGENT_IDS},
        log_dir=log_dir
    )
elif config["policy_manager"]["policy_training_mode"] == "multi-node":
    policy_manager = MultiNodePolicyManager(
        policies,
        {id_: f"TRAINER.{id_ % NUM_POLICY_TRAINERS}" for id_ in AGENT_IDS}, # policy-trainer mapping
        config["policy_manager"]["group"],
        proxy_kwargs={"redis_address": (config["redis"]["host"], config["redis"]["port"])},
        log_dir=log_dir
    )
