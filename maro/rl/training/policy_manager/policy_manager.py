# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import time
from abc import ABC, abstractmethod
from collections import defaultdict
from multiprocessing import Pipe, Process
from os import getcwd
from typing import Callable, Dict, List

from maro.communication import Proxy, SessionMessage, SessionType
from maro.rl.experience import ExperienceSet
from maro.rl.policy import AbsCorePolicy, AbsPolicy
from maro.utils import Logger

from ..message_enums import MsgKey, MsgTag
from .trainer import trainer_process


class AbsPolicyManager(ABC):
    """Manage all policies.

    The actual policy instances may reside here or be distributed on a set of processes or remote nodes.

    Args:
        policies (List[AbsPolicy]): A list of policies managed by the manager.
    """
    def __init__(self, policies: List[AbsPolicy]):
        for policy in policies:
            if not isinstance(policy, AbsCorePolicy):
                raise ValueError("Only 'AbsCorePolicy' instances can be managed by a policy manager.")

        super().__init__()
        self.policy_dict = {policy.name: policy for policy in policies}
        self.updated = set(self.policy_dict.keys())
        self._version = 0

    @property
    def version(self):
        return self._version

    @abstractmethod
    def on_experiences(self, exp_by_policy: Dict[str, ExperienceSet]):
        """Logic for handling incoming experiences is implemented here."""
        raise NotImplementedError

    def get_state(self):
        return {name: self.policy_dict[name].get_state() for name in self.updated}

    def reset_update_status(self):
        self.updated.clear()


class LocalPolicyManager(AbsPolicyManager):
    """Policy manager that contains the actual policy instances.

    Args:
        policies (List[AbsPolicy]): A list of policies managed by the manager.
        log_dir (str): Directory to store logs in. A ``Logger`` with tag "LEARNER" will be created at init time
            and this directory will be used to save the log files generated by it. Defaults to the current working
            directory.
    """
    def __init__(self, policies: List[AbsPolicy], log_dir: str = getcwd()):
        super().__init__(policies)
        self._logger = Logger("LOCAL_TRAINING_MANAGER", dump_folder=log_dir)
        self._new_exp_counter = defaultdict(int)

    def on_experiences(self, exp_by_policy: Dict[str, ExperienceSet]):
        """Store experiences and update policies if possible.

        The incoming experiences are expected to be grouped by policy ID and will be stored in the corresponding
        policy's experience manager. Policies whose update conditions have been met will then be updated.
        """
        t0 = time.time()
        for policy_name, exp in exp_by_policy.items():
            if (
                isinstance(self.policy_dict[policy_name], AbsCorePolicy) and
                self.policy_dict[policy_name].on_experiences(exp)
            ):
                self.updated.add(policy_name)

        if self.updated:
            self._logger.info(f"Updated policies {self.updated}")

        self._logger.debug(f"policy update time: {time.time() - t0}")


class MultiProcessPolicyManager(AbsPolicyManager):
    """Policy manager that spawns a set of trainer processes for parallel training.

    Args:
        policies (List[AbsPolicy]): A list of policies managed by the manager.
        policy2trainer (dict): Mapping from policy names to trainer IDs.
        create_policy_func_dict (dict): A dictionary mapping policy names to functions that create them. The policy
            creation function should have exactly one parameter which is the policy name and return an ``AbsPolicy``
            instance.
        log_dir (str): Directory to store logs in. A ``Logger`` with tag "LOCAL_ROLLOUT_MANAGER" will be created at
            init time and this directory will be used to save the log files generated by it. Defaults to the current
            working directory.
    """
    def __init__(
        self,
        policies: List[AbsPolicy],
        policy2trainer: Dict[str, str],
        create_policy_func_dict: Dict[str, Callable],
        log_dir: str = getcwd(),
    ):
        super().__init__(policies)
        self._logger = Logger("POLICY_MANAGER", dump_folder=log_dir)
        self.policy2trainer = policy2trainer
        self._trainer2policies = defaultdict(list)
        for policy_name, trainer_id in policy2trainer.items():
            self._trainer2policies[trainer_id].append(policy_name)

        self._trainer_processes = []
        self._manager_end = {}
        for trainer_id, policy_names in self._trainer2policies.items():
            manager_end, trainer_end = Pipe()
            self._manager_end[trainer_id] = manager_end
            trainer = Process(
                target=trainer_process,
                args=(
                    trainer_id,
                    trainer_end,
                    {name: create_policy_func_dict[name] for name in policy_names},
                    {name: self.policy_dict[name].get_state() for name in self._trainer2policies[trainer_id]}
                ),
                kwargs={"log_dir": log_dir}
            )
            self._trainer_processes.append(trainer)
            trainer.start()

    def on_experiences(self, exp_by_policy: Dict[str, ExperienceSet]):
        for trainer_id, conn in self._manager_end.items():
            conn.send({
                "type": "train",
                "experiences": {name: exp_by_policy[name] for name in self._trainer2policies[trainer_id]}
            })

        for conn in self._manager_end.values():
            result = conn.recv()
            for policy_name, policy_state in result["policy"].items():
                self.policy_dict[policy_name].set_state(policy_state)
                self.updated.add(policy_name)

        if self.updated:
            self._version += 1

    def exit(self):
        """Tell the trainer processes to exit."""
        for conn in self._manager_end.values():
            conn.send({"type": "quit"})


class MultiNodePolicyManager(AbsPolicyManager):
    """Policy manager that communicates with a set of remote nodes for parallel training.

    Args:
        policies (List[AbsPolicy]): A list of policies managed by the manager.
        policy2trainer (dict): Mapping from policy names to trainer IDs.
        create_policy_func_dict (dict): A dictionary mapping policy names to functions that create them. The policy
            creation function should have exactly one parameter which is the policy name and return an ``AbsPolicy``
            instance.
        group (str): Group name for the training cluster, which includes all trainers and a training manager that
            manages them.
        proxy_kwargs: Keyword parameters for the internal ``Proxy`` instance. See ``Proxy`` class
            for details. Defaults to the empty dictionary.
        log_dir (str): Directory to store logs in. A ``Logger`` with tag "LOCAL_ROLLOUT_MANAGER" will be created at
            init time and this directory will be used to save the log files generated by it. Defaults to the current
            working directory.
    """
    def __init__(
        self,
        policies: List[AbsPolicy],
        policy2trainer: Dict[str, str],
        group: str,
        proxy_kwargs: dict = {},
        log_dir: str = getcwd()
    ):
        super().__init__(policies)
        self._logger = Logger("POLICY_MANAGER", dump_folder=log_dir)
        self.policy2trainer = policy2trainer
        self._trainer2policies = defaultdict(list)
        for policy_name, trainer_name in self.policy2trainer.items():
            self._trainer2policies[trainer_name].append(policy_name)
        peers = {"trainer": len(set(self.policy2trainer.values()))}
        self._proxy = Proxy(group, "policy_manager", peers, **proxy_kwargs)
        for trainer_name, policy_names in self._trainer2policies.items():
            self._proxy.send(
                SessionMessage(
                    MsgTag.INIT_POLICY_STATE, self._proxy.name, trainer_name,
                    body={MsgKey.POLICY_STATE: {name: self.policy_dict[name].get_state() for name in policy_names}}
                )
            )

    def on_experiences(self, exp_by_policy: Dict[str, ExperienceSet]):
        msg_body_by_dest = defaultdict(dict)
        for policy_name, exp in exp_by_policy.items():
            trainer_id = self.policy2trainer[policy_name]
            if MsgKey.EXPERIENCES not in msg_body_by_dest[trainer_id]:
                msg_body_by_dest[trainer_id][MsgKey.EXPERIENCES] = {}
            msg_body_by_dest[trainer_id][MsgKey.EXPERIENCES][policy_name] = exp

        for reply in self._proxy.scatter(MsgTag.TRAIN, SessionType.TASK, list(msg_body_by_dest.items())):
            for policy_name, policy_state in reply.body[MsgKey.POLICY_STATE].items():
                self.policy_dict[policy_name].set_state(policy_state)
                self.updated.add(policy_name)

        if self.updated:
            self._version += 1

    def exit(self):
        """Tell the remote trainers to exit."""
        self._proxy.ibroadcast("trainer", MsgTag.EXIT, SessionType.NOTIFICATION)
        self._proxy.close()
        self._logger.info("Exiting...")
