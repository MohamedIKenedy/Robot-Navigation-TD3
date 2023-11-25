"""
Implementation of experience replay
Author: Mohamed IFQIR
"""

import random
from collections import deque
import numpy as np

class ReplayBuffer(object):
    def __init__(self, buffer_size, random_seed=123):
        """
        Initialize the ReplayBuffer with a specified buffer size.
        The right side of the deque contains the most recent experiences.
        
        Args:
            buffer_size (int): Maximum number of experiences to store in the buffer.
            random_seed (int): Seed for random number generator.
        """
        self.buffer_size = buffer_size
        self.count = 0
        self.buffer = deque()
        random.seed(random_seed)

    def add(self, s, a, r, t, s2):
        """
        Add a new experience to the replay buffer.

        Args:
            s (array): Current state.
            a (array): Chosen action.
            r (float): Reward received.
            t (bool): Terminal state indicator.
            s2 (array): Next state.
        """
        experience = (s, a, r, t, s2)
        if self.count < self.buffer_size:
            self.buffer.append(experience)
            self.count += 1
        else:
            self.buffer.popleft()
            self.buffer.append(experience)

    def sample_batch(self, batch_size):
        """
        Sample a batch of experiences from the replay buffer.

        Args:
            batch_size (int): Number of experiences to sample.

        Returns:
            tuple: A tuple containing arrays of state, action, reward, terminal flag, and next state.
        """
        batch = []

        if self.count < batch_size:
            batch = random.sample(self.buffer, self.count)
        else:
            batch = random.sample(self.buffer, batch_size)

        s_batch = np.array([_[0] for _ in batch])
        a_batch = np.array([_[1] for _ in batch])
        r_batch = np.array([_[2] for _ in batch]).reshape(-1, 1)
        t_batch = np.array([_[3] for _ in batch]).reshape(-1, 1)
        s2_batch = np.array([_[4] for _ in batch])

        return s_batch, a_batch, r_batch, t_batch, s2_batch

    def size(self):
        """
        Get the current size of the replay buffer.

        Returns:
            int: Number of experiences in the buffer.
        """
        return self.count

    def clear(self):
        """
        Clear the contents of the replay buffer.
        """
        self.buffer.clear()
        self.count = 0
