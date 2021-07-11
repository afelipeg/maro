# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from abc import ABC, abstractmethod

from maro.rl.experience import ExperienceManager, ExperienceSet
from maro.rl.exploration import AbsExploration


class AbsPolicy(ABC):
    """Abstract policy class."""
    def __init__(self):
        super().__init__()

    @abstractmethod
    def choose_action(self, state):
        raise NotImplementedError


class NullPolicy(AbsPolicy):
    """Dummy policy that does nothing.

    Note that the meaning of a "None" action may depend on the scenario.
    """
    def choose_action(self, state):
        return None


class AbsCorePolicy(AbsPolicy):
    """Policy that can update itself using simulation experiences.

    Reinforcement learning (RL) policies should inherit from this.

    Args:
        experience_manager (ExperienceManager): An experience manager for storing and retrieving experiences
            for training.
        exploration (AbsExploration): Exploration strategy for generating exploratory actions. Defaults to None.
    """
    def __init__(self, experience_manager: ExperienceManager, exploration: AbsExploration = None):
        super().__init__()
        self.experience_manager = experience_manager
        self.exploration = exploration
        self.exploring = True

    @abstractmethod
    def choose_action(self, state):
        raise NotImplementedError

    @abstractmethod
    def learn(self):
        """Policy update logic is implemented here.

        This usually includes retrieving experiences as training samples from the experience manager and
        updating the underlying models using these samples.
        """
        raise NotImplementedError

    @abstractmethod
    def get_state(self):
        """Return the current state of the policy.

        The implementation must be in correspondence with that of ``set_state``. For example, if a torch model
        is contained in the policy, ``get_state`` may include a call to ``state_dict()`` on the model, while
        ``set_state`` should accordingly include ``load_state_dict()``.
        """
        pass

    @abstractmethod
    def set_state(self, policy_state):
        """Set the policy state to ``policy_state``.

        The implementation must be in correspondence with that of ``get_state``. For example, if a torch model
        is contained in the policy, ``set_state`` may include a call to ``load_state_dict()`` on the model, while
        ``get_state`` should accordingly include ``state_dict()``.
        """
        pass

    def store(self, exp: ExperienceSet) -> bool:
        """
        Store incoming experiences and update if necessary.
        """
        self.experience_manager.put(exp)
        # print(
        #     f"exp mem size = {self.experience_manager.size}, incoming: {exp.size}, new exp = {self._new_exp_counter}"
        # )

    def exploit(self):
        self.exploring = False

    def explore(self):
        self.exploring = True

    def exploration_step(self):
        if self.exploration:
            self.exploration.step()

    def load(self, path: str):
        """Load the policy state from disk."""
        pass

    def save(self, path: str):
        """Save the policy state to disk."""
        pass
