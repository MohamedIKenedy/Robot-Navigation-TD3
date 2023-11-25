"""
Implementation of TD3 (Twin Delayed Deep Deterministic Policy Gradient) algorithm for Reinforcement Learning
Author: Mohamed IFQIR
"""

import os
import time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from numpy import inf
from torch.utils.tensorboard import SummaryWriter
from replay_buffer import ReplayBuffer
from velodyne_environment import GazeboEnv
import matplotlib.pyplot as plt
from geometry_msgs.msg import Twist
from std_msgs.msg import Empty
import rospy 


cmd_vel_pub = rospy.Publisher("/cmd_vel", Twist, queue_size=1)



def evaluate(network, epoch, eval_episodes=10):
    avg_reward = 0.0
    col = 0
    for _ in range(eval_episodes):
        count = 0
        state = env.reset()
        done = False
        while not done and count < 501:
            action = network.get_action(np.array(state))
            a_in = [(action[0] + 1) / 2, action[1]]
            state, reward, done, _ = env.step(a_in)
            avg_reward += reward
            count += 1
            if reward < -90:
                col += 1
    avg_reward /= eval_episodes
    avg_col = col / eval_episodes
    print("..............................................")
    print(
        "Avgerage Reward over %i Evaluation Episodes, Epoch %i: %f, %f"
        % (eval_episodes, epoch, avg_reward, avg_col)
    )
    print("..............................................")
    return avg_reward

# Define Constants and Hyperparameters
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
seed = 0
eval_freq = 5000
max_ep = 500
eval_ep = 10
max_timesteps = 50000000
exploration_noise = 1
exploration_decay_steps = 500000
min_exploration = 0.1
batch_size = 40
discount_factor = 0.999999
target_update_rate = 0.005
policy_noise = 0.2
noise_clip = 0.5
policy_update_freq = 2
buffer_size = 10000000
model_file_name = "TD3_velodyne"
save_model = True
load_model = False
random_near_obstacle = True

# Set Random Seed
torch.manual_seed(seed)
np.random.seed(seed)

# Create Network Storage Folders
if not os.path.exists("./results"):
    os.makedirs("./results")
if save_model and not os.path.exists("./models"):
    os.makedirs("./models")

# Create Training Environment
env_dim = 20
robot_dim = 4
env = GazeboEnv("multi_robot_scenario.launch", env_dim)
time.sleep(5)
state_dim = env_dim + robot_dim
action_dim = 2
max_action_value = 1

# Define Actor Network
class Actor(nn.Module):
    def __init__(self, state_dim, action_dim):
        super(Actor, self).__init__()
        # Network architecture
        self.layer_1 = nn.Linear(state_dim, 800)
        self.layer_2 = nn.Linear(800, 600)
        self.layer_3 = nn.Linear(600, action_dim)
        self.tanh = nn.Tanh()

    def forward(self, state):
        state = F.relu(self.layer_1(state))
        state = F.relu(self.layer_2(state))
        action = self.tanh(self.layer_3(state))
        return action

# Define Critic Network
class Critic(nn.Module):
    def __init__(self, state_dim, action_dim):
        super(Critic, self).__init__()
        # First Critic Network
        self.layer_1 = nn.Linear(state_dim, 800)
        self.layer_2_state = nn.Linear(800, 600)
        self.layer_2_action = nn.Linear(action_dim, 600)
        self.layer_3 = nn.Linear(600, 1)
        # Second Critic Network
        self.layer_4 = nn.Linear(state_dim, 800)
        self.layer_5_state = nn.Linear(800, 600)
        self.layer_5_action = nn.Linear(action_dim, 600)
        self.layer_6 = nn.Linear(600, 1)

    def forward(self, state, action):
        state1 = F.relu(self.layer_1(state))
        self.layer_2_state(state1)
        self.layer_2_action(action)
        state2 = torch.mm(state1, self.layer_2_state.weight.data.t())
        action2 = torch.mm(action, self.layer_2_action.weight.data.t())
        state2 = F.relu(state2 + action2 + self.layer_2_action.bias.data)
        q1_value = self.layer_3(state2)

        state3 = F.relu(self.layer_4(state))
        self.layer_5_state(state3)
        self.layer_5_action(action)
        state4 = torch.mm(state3, self.layer_5_state.weight.data.t())
        action4 = torch.mm(action, self.layer_5_action.weight.data.t())
        state4 = F.relu(state4 + action4 + self.layer_5_action.bias.data)
        q2_value = self.layer_6(state4)
        return q1_value, q2_value

# Define TD3 Algorithm
class TD3(object):
    def __init__(self, state_dim, action_dim, max_action):
        # Initialize Actor and Critic networks
        self.actor = Actor(state_dim, action_dim).to(device)
        self.actor_target = Actor(state_dim, action_dim).to(device)
        self.actor_target.load_state_dict(self.actor.state_dict())
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters())

        self.critic = Critic(state_dim, action_dim).to(device)
        self.critic_target = Critic(state_dim, action_dim).to(device)
        self.critic_target.load_state_dict(self.critic.state_dict())
        self.critic_optimizer = torch.optim.Adam(self.critic.parameters())

        self.max_action = max_action
        self.writer = SummaryWriter()
        self.iter_count = 0

    def get_action(self, state):
        # Get action from the Actor network
        state = torch.Tensor(state.reshape(1, -1)).to(device)
        return self.actor(state).cpu().data.numpy().flatten()

    def train(
        self,
        replay_buffer,
        iterations,
        batch_size=200,
        discount=1,
        tau=0.005,
        policy_noise=0.2,
        noise_clip=0.5,
        policy_update_freq=2,
    ):
        # Training loop
        average_Q_value = 0
        max_Q_value = -inf
        average_loss = 0
        for it in range(iterations):
            # Sample a batch from the replay buffer
            (
                batch_states,
                batch_actions,
                batch_rewards,
                batch_dones,
                batch_next_states,
            ) = replay_buffer.sample_batch(batch_size)
            state = torch.Tensor(batch_states).to(device)
            next_state = torch.Tensor(batch_next_states).to(device)
            action = torch.Tensor(batch_actions).to(device)
            reward = torch.Tensor(batch_rewards).to(device)
            done = torch.Tensor(batch_dones).to(device)

            # Obtain the estimated action from the next state using the actor-target
            next_action = self.actor_target(next_state)

            # Add noise to the action
            noise = torch.Tensor(batch_actions).data.normal_(0, policy_noise).to(device)
            noise = noise.clamp(-noise_clip, noise_clip)
            next_action = (next_action + noise).clamp(-self.max_action, self.max_action)

            # Calculate Q values from critic-target network for the next state-action pair
            target_Q1, target_Q2 = self.critic_target(next_state, next_action)

            # Select the minimal Q value from the two calculated values
            target_Q = torch.min(target_Q1, target_Q2)
            average_Q_value += torch.mean(target_Q)
            max_Q_value = max(max_Q_value, torch.max(target_Q))

            # Calculate final Q value from target network parameters using Bellman equation
            target_Q = reward + ((1 - done) * discount * target_Q).detach()

            # Get Q values of the basis networks with current parameters
            current_Q1, current_Q2 = self.critic(state, action)

            # Calculate loss between current Q value and target Q value
            loss = F.mse_loss(current_Q1, target_Q) + F.mse_loss(current_Q2, target_Q)
            
            # Perform gradient descent for Critic network
            self.critic_optimizer.zero_grad()
            loss.backward()
            self.critic_optimizer.step()

            if it % policy_update_freq == 0:
                # Maximize the actor output value by performing gradient ascent on negative Q values
                actor_gradient, _ = self.critic(state, self.actor(state))
                actor_gradient = -actor_gradient.mean()
                self.actor_optimizer.zero_grad()
                actor_gradient.backward()
                self.actor_optimizer.step()

                # Use soft update to update actor-target network parameters
                for param, target_param in zip(
                    self.actor.parameters(), self.actor_target.parameters()
                ):
                    target_param.data.copy_(
                        tau * param.data + (1 - tau) * target_param.data
                    )
                # Use soft update to update critic-target network parameters
                for param, target_param in zip(
                    self.critic.parameters(), self.critic_target.parameters()
                ):
                    target_param.data.copy_(
                        tau * param.data + (1 - tau) * target_param.data
                    )

            average_loss += loss
        self.iter_count += 1
        # Write new values for tensorboard
        self.writer.add_scalar("Loss", average_loss / iterations, self.iter_count)
        self.writer.add_scalar("Average_Q_Value", average_Q_value / iterations, self.iter_count)
        self.writer.add_scalar("Max_Q_Value", max_Q_value, self.iter_count)

    def save(self, filename, directory):
        torch.save(self.actor.state_dict(), "%s/%s_actor.pth" % (directory, filename))
        torch.save(self.critic.state_dict(), "%s/%s_critic.pth" % (directory, filename))

    def load(self, filename, directory):
        self.actor.load_state_dict(
            torch.load("%s/%s_actor.pth" % (directory, filename))
        )
        self.critic.load_state_dict(
            torch.load("%s/%s_critic.pth" % (directory, filename))
        )

# Create TD3 Network
network = TD3(state_dim, action_dim, max_action_value)

# Create Replay Buffer
replay_buffer = ReplayBuffer(buffer_size, seed)

# Load Pre-trained Model
if load_model:
    try:
        network.load(model_file_name, "./models")
    except:
        print("Could not load the stored model parameters, initializing training with random parameters")

# Create Evaluation Data Store
evaluations = []

timestep = 0
timesteps_since_eval = 0
episode_num = 0
done = True
epoch = 1

count_rand_actions = 0
random_action = []

# Training Loop
while timestep < max_timesteps:

    # On termination of episode
    if done:
        if timestep != 0:
            network.train(
                replay_buffer,
                episode_timesteps,
                batch_size,
                discount_factor,
                target_update_rate,
                policy_noise,
                noise_clip,
                policy_update_freq,
            )

        if timesteps_since_eval >= eval_freq:
            print("Validating")
            timesteps_since_eval %= eval_freq
            evaluations.append(
                evaluate(network=network, epoch=epoch, eval_episodes=eval_ep)
            )
            network.save(model_file_name, directory="./models")
            np.save("./results/%s" % (model_file_name), evaluations)
            epoch += 1

        state = env.reset()
        done = False

        episode_reward = 0
        episode_timesteps = 0
        episode_num += 1

    # Add exploration noise
    if exploration_noise > min_exploration:
        exploration_noise = exploration_noise - ((1 - min_exploration) / exploration_decay_steps)

    # Implement obstacle avoidance logic
    obstacle_distance_threshold = 0.5  # Set a threshold distance for obstacle detection

    if min(state[4:-8]) < obstacle_distance_threshold:
        # Calculate desired linear and angular velocities to avoid the obstacle
        linear_velocity = 0.0  # Stop to avoid collision
        angular_velocity = 1.0  # Rotate to avoid the obstacle
    else:
        # No obstacle nearby, continue moving forward
        linear_velocity = 0.5  # Move forward
        angular_velocity = 0.0  # No rotation

    action = network.get_action(np.array(state))
    action = (action + np.random.normal(0, exploration_noise, size=action_dim)).clip(
        -max_action_value, max_action_value
    )

    # Apply the chosen velocity commands
    cmd_vel_msg = Twist()
    cmd_vel_msg.linear.x = linear_velocity
    cmd_vel_msg.angular.z = angular_velocity
    cmd_vel_pub.publish(cmd_vel_msg)

    # Normalize action to range [0, 1] for linear velocity and [-1, 1] for angular velocity
    normalized_action = [(action[0] + 1) / 2, action[1]]
    next_state, reward, done, target = env.step(normalized_action)
    done_bool = 0 if episode_timesteps + 1 == max_ep else int(done)
    done = 1 if episode_timesteps + 1 == max_ep else int(done)
    episode_reward += reward

    # Save tuple in replay buffer
    replay_buffer.add(state, action, reward, done_bool, next_state)

    # Update counters
    state = next_state
    episode_timesteps += 1
    timestep += 1
    timesteps_since_eval += 1
    evaluate(network=network, epoch=epoch, eval_episodes=eval_ep)

print("Training completed !!")

# After training, evaluate and save the network
evaluations.append(evaluate(network=network, epoch=epoch, eval_episodes=eval_ep))
if save_model:
    network.save("%s" % model_file_name, directory="./models")
np.save("./results/%s" % model_file_name, evaluations)

# # Plot the evaluation results
# plt.plot(range(len(evaluations)), evaluations, label="Average Reward")
# plt.xlabel("Epoch")
# plt.ylabel("Average Reward")
# plt.title("Evaluation Results")
# plt.legend()
# plt.grid(True)
# plt.show()