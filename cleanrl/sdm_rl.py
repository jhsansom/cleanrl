# docs and experiment results can be found at https://docs.cleanrl.dev/rl-algorithms/dqn/#dqn_jaxpy
import argparse
import os
import random
import time
from distutils.util import strtobool
import matplotlib.pyplot as plt

import math
import flax
import flax.linen as nn
import gymnasium as gym
import jax
import jax.numpy as jnp
import numpy as np
import optax
from flax.training.train_state import TrainState
from stable_baselines3.common.buffers import ReplayBuffer
from torch.utils.tensorboard import SummaryWriter

def parse_args():
    # fmt: off
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp-name", type=str, default=os.path.basename(__file__).rstrip(".py"),
        help="the name of this experiment")
    parser.add_argument("--seed", type=int, default=1,
        help="seed of the experiment")
    parser.add_argument("--track", type=lambda x: bool(strtobool(x)), default=False, nargs="?", const=True,
        help="if toggled, this experiment will be tracked with Weights and Biases")
    parser.add_argument("--wandb-project-name", type=str, default="cleanRL",
        help="the wandb's project name")
    parser.add_argument("--wandb-entity", type=str, default=None,
        help="the entity (team) of wandb's project")
    parser.add_argument("--capture-video", type=lambda x: bool(strtobool(x)), default=False, nargs="?", const=True,
        help="whether to capture videos of the agent performances (check out `videos` folder)")
    parser.add_argument("--save-model", type=lambda x: bool(strtobool(x)), default=False, nargs="?", const=True,
        help="whether to save model into the `runs/{run_name}` folder")
    parser.add_argument("--upload-model", type=lambda x: bool(strtobool(x)), default=False, nargs="?", const=True,
        help="whether to upload the saved model to huggingface")
    parser.add_argument("--hf-entity", type=str, default="",
        help="the user or org name of the model repository from the Hugging Face Hub")

    # Algorithm specific arguments
    parser.add_argument("--env-id", type=str, default="CartPole-v1",
        help="the id of the environment")
    parser.add_argument("--total-timesteps", type=int, default=500000,
        help="total timesteps of the experiments")
    parser.add_argument("--learning-rate", type=float, default=2.5e-4,
        help="the learning rate of the optimizer")
    parser.add_argument("--num-envs", type=int, default=1,
        help="the number of parallel game environments")
    parser.add_argument("--buffer-size", type=int, default=10000,
        help="the replay memory buffer size")
    parser.add_argument("--gamma", type=float, default=0.99,
        help="the discount factor gamma")
    parser.add_argument("--tau", type=float, default=1.,
        help="the target network update rate")
    parser.add_argument("--target-network-frequency", type=int, default=500,
        help="the timesteps it takes to update the target network")
    parser.add_argument("--batch-size", type=int, default=128,
        help="the batch size of sample from the reply memory")
    parser.add_argument("--start-e", type=float, default=1,
        help="the starting epsilon for exploration")
    parser.add_argument("--end-e", type=float, default=0.05,
        help="the ending epsilon for exploration")
    parser.add_argument("--exploration-fraction", type=float, default=0.5,
        help="the fraction of `total-timesteps` it takes from start-e to go end-e")
    parser.add_argument("--learning-starts", type=int, default=10000,
        help="timestep to start learning")
    parser.add_argument("--train-frequency", type=int, default=10,
        help="the frequency of training")
    
    # Flags specific to SDM-RL paper

    # The neural architecture to use
    # - baseline
    # - DSOM
    # - SDM
    parser.add_argument("--architecture", type=str, default=10,
        help="the type of model architecture used")

    # Whether to use SARSA or Q-learning
    # - SARSA
    # - QLEARNING
    parser.add_argument("--bellman-update", type=str, default=10,
        help="the type of Bellman equation used: SARSA or QLEARNING")
    
    # The optimizer to be used
    # - ADAM
    # - RMSPROP
    # - SGD
    parser.add_argument("--optimizer", type=str, default=10,
        help="the optimizer used")
    
    # Number of hidden units
    parser.add_argument("--hidden-size", type=int, default=800,
        help="the size of the hidden layer")
    

    # Which epsilon scheduler to use
    # - LINEAR
    # - EXPONENTIAL
    parser.add_argument("--eps-scheduler", type=str, default='LINEAR',
        help="which scheduler you use")
    
    # Epsilon decay rate
    parser.add_argument("--eps-decay", type=float, default=0.995,
        help="if using exponential epsilon scheduler, the decay rate")
    
    # Number of neurons in sparse layer
    parser.add_argument("--sparse-dim", type=int, default=128,
        help="if using sparsity, the number of neurons")
    
    # Learning rate for DSOM updates
    parser.add_argument("--dsom-lr", type=float, default=0.05,
        help="learning rate for DSOM updates")
    
    # Elasticity for DSOM updates
    parser.add_argument("--elasticity", type=float, default=0.05,
        help="elasticity for DSOM updates")
    
    # Elasticity for DSOM updates
    parser.add_argument("--plot-som", type=int, default=-1,
        help="whether or not to plot SOM vectors")
    

    args = parser.parse_args()
    # fmt: on
    assert args.num_envs == 1, "vectorized envs are not supported at the moment"

    return args


def make_env(env_id, seed, idx, capture_video, run_name):
    def thunk():
        if capture_video and idx == 0:
            env = gym.make(env_id, render_mode="rgb_array")
            env = gym.wrappers.RecordVideo(env, f"videos/{run_name}")
        else:
            env = gym.make(env_id)
        env = gym.wrappers.RecordEpisodeStatistics(env)
        env.action_space.seed(seed)

        return env

    return thunk


# TODO: change the core architecture, plus add new ones corresponding to SDM and DSOM
# ALGO LOGIC: initialize agent here:
class QNetwork(nn.Module):
    action_dim: int

    @nn.compact
    def __call__(self, x: jnp.ndarray):
        x = nn.Dense(args.hidden_size)(x)
        x = nn.relu(x)
        x = nn.Dense(self.action_dim)(x)
        return x
    
def global_max(x):
    return jnp.max(jnp.ravel(x))
    

class DSOM(nn.Module):
    action_dim: int
    obs_dim: int
    max_dist = 0
    elasticity = 0.5
    lr = 0.025

    def setup(self):
        self.k = 0.5

        self.som_codebook_vecs = self.param('som_codebook_vecs', nn.initializers.normal(0.5), (args.hidden_size, self.obs_dim))

        def constant_initializer(key, grid_dim):
            grid_dim = int(grid_dim)
            x, y = jnp.meshgrid(jnp.arange(grid_dim), jnp.arange(grid_dim))
            x = jnp.ravel(x).astype(float)
            y = jnp.ravel(y).astype(float)
            return jnp.stack((x,y), axis=1)


        self.som_addresses = self.param('som_addresses', constant_initializer, math.sqrt(args.hidden_size))


        self.dense1 = nn.Dense(args.hidden_size)
        self.dense2 = nn.Dense(self.action_dim)

    def __call__(self, x: jnp.ndarray):
        # First layer of NN
        hidden = self.dense1(x)
        hidden = nn.relu(hidden)

        # Pass through SOM layer
        som_outputs = jax.lax.stop_gradient(self.som_layer(x))

        # Hadamard product
        layer2 = hidden * som_outputs

        # Final dense layer
        output = self.dense2(layer2)

        return output

    def som_layer(self, x: jnp.ndarray):

        # Align both so that the dimensionality is (batch_dim, neuron_dim, obs_dim)
        x = jnp.expand_dims(x, 1)
        codebook_vecs_expanded = jnp.expand_dims(self.som_codebook_vecs, 0)

        # Perform the actual calculations
        dists = jnp.sqrt(jnp.sum((codebook_vecs_expanded - x)**2, axis=-1))
        mask = jnp.exp(-dists/self.k)
        
        # Mask has shape (batch_dim, neuron_dim)
        return mask
    
    def dsom_update(self, params, obs, mode='avg'):

        cb_vecs = params['params']['som_codebook_vecs'] # (neuron_dim, obs_dim)
        addresses = params['params']['som_addresses'] # (neuron_dim, obs_dim)

        # Get normalized distance metric
        cb_vecs_copy = jnp.expand_dims(cb_vecs, 1) # (neuron_dim, 1, obs_dim)
        cb_vecs = jnp.expand_dims(cb_vecs, 0) # (1, neuron_dim, obs_dim)
        x = jnp.linalg.norm(cb_vecs_copy - cb_vecs, axis=-1) # (neuron_dim, neuron_dim)
        current_max_dist = jnp.max(jnp.ravel(x)) # scalar
        self.max_dist = jnp.max(jnp.array([current_max_dist, self.max_dist])) # scalar

        # Align observations array
        obs = jnp.expand_dims(obs, 1) # (batch_dim, 1, obs_dim)

        # Calculate euclidean norm distances
        diff = (obs - cb_vecs) # (batch_dim, neuron_dim, obs_dim)

        dist = jnp.linalg.norm(diff, axis=-1) # (batch_dim, neuron_dim)
        #jnp.sum(diff**2, axis=-1) 

        # Calculate winner for each batch sample 
        winner_idx = jnp.argmin(dist, axis=1) # (batch_dim)

        # Calculate normalized euclidean norm distances
        dist_normed = dist / self.max_dist # (batch_dim, neuron_dim)
        
        # Calculate h numerator
        winner_addresses = addresses[winner_idx, :] # (batch_dim, obs_dim)
        winner_addresses = jnp.expand_dims(winner_addresses, 1) # (batch_dim, 1, obs_dim)
        addresses = jnp.expand_dims(addresses, 0) # (1, neuron_dim, obs_dim)
        numerators = jnp.sum((addresses - winner_addresses)**2, axis=-1) # (batch_dim, neuron_dim)

        # Calculate h denominator
        winner_cb_vecs = cb_vecs[winner_idx, :] # (batch_dim, obs_dim)
        denominators = self.elasticity**2 * (jnp.linalg.norm(obs - winner_cb_vecs, axis=-1) / self.max_dist)**2 # (batch_dim, neuron_dim)
        
        # Calculate h overall
        h = jnp.exp(- numerators / denominators) # (batch_dim, obs_dim)
        
        # Calculate change in weights
        dist_normed = jnp.expand_dims(dist_normed, -1) # (batch_dim, neuron_dim, 1)
        h = jnp.expand_dims(h, -1) # (batch_dim, neuron_dim, 1)
        delta_w_batch = self.lr * dist_normed * h * diff # (batch_dim, neuron_dim, obs_dim)

        # Collapse batch dimension
        if mode == 'avg':
            delta_w = jnp.average(delta_w_batch, axis=0) # (neuron_dim, obs_dim)
        elif mode == 'sum':
            delta_w = jnp.sum(delta_w_batch, axis=0) # (neuron_dim, obs_dim)
        else:
            raise Exception('Invalid update mode')
        
        # Clip vector to prevent explosion
        delta_w = jnp.clip(delta_w, -1, 1)
        
        # Apply update vector
        new_cb_vecs = cb_vecs.squeeze() + delta_w

        return new_cb_vecs
    
class SDM(nn.Module):
    action_dim: int
    obs_dim: int
    max_dist = 0
    elasticity = 0.5
    lr = 0.025

    def setup(self):
        self.k = 0.995

        # hidden_size : size of keys and values
        # sparse_dim : number of neurons

        self.sdm_values = self.param('sdm_values', nn.initializers.normal(0.5), (args.sparse_dim, args.hidden_size))
        self.sdm_keys = self.param('sdm_keys', nn.initializers.uniform(1.0), (args.hidden_size, args.sparse_dim))

        # Normalize and clip positive
        self.sdm_keys = jnp.maximum(self.sdm_keys, 0)
        self.sdm_keys = self.sdm_keys / jnp.linalg.norm(self.sdm_keys, axis=0)
        self.sdm_values = jnp.maximum(self.sdm_values, 0)

        self.dense1 = nn.Dense(args.hidden_size)
        self.dense2 = nn.Dense(self.action_dim)

    def __call__(self, x: jnp.ndarray):
        # First layer of NN
        hidden = self.dense1(x)
        hidden = nn.relu(hidden)

        # Pass through SDM layer
        hidden2 = self.sdm_layer(hidden)

        # Final dense layer
        output = self.dense2(hidden2)

        return output

    def sdm_layer(self, x: jnp.ndarray):

        # Normalization steps
        x = x / jnp.linalg.norm(x, axis=-1)
        
        # Get activations
        activations = jnp.matmul(x, self.sdm_keys) # (batch_dim, sparse_dim)

        # Get the top k
        k_abs = math.ceil(self.k*args.hidden_size) + 1
        sorted_activations = jnp.sort(activations, axis=-1)
        min_activation = jnp.squeeze(sorted_activations[:, -k_abs])
        activations = jnp.maximum(activations - min_activation, 0) # (batch_dim, sparse_dim)

        # Get layer output
        return jnp.matmul(activations, self.sdm_values)
    
    def sdm_update(self, params):
        sdm_keys = params['params']['sdm_keys']
        sdm_values = params['params']['sdm_values']
        sdm_keys = jnp.maximum(sdm_keys, 0)
        sdm_keys = sdm_keys / jnp.linalg.norm(sdm_keys, axis=0)
        sdm_values = jnp.maximum(sdm_values, 0)

        return (sdm_keys, sdm_values)


def plot_codebook_vecs(vecs, num, obs):
    x = vecs[:,0]
    y = vecs[:,1]

    plt.figure()
    plt.xlim(-2, 2)
    plt.ylim(-2, 2)
    plt.scatter(obs[:,0], obs[:,1], color='blue', alpha=0.5)
    plt.scatter(x, y, alpha=0.1, color='red')
    filename = '/Users/jakesansom/Desktop/cleanrl/testfigs/' + str(num) + '.png'
    plt.savefig(filename)

class TrainState(TrainState):
    target_params: flax.core.FrozenDict

# TODO: does this need to be an exponential scheduler instead?
def linear_schedule(start_e: float, end_e: float, duration: int, t: int):
    slope = (end_e - start_e) / duration
    return max(slope * t + start_e, end_e)

def exponential_schedule(start_e: float, end_e: float, decay: int, t: int):
    eps = start_e * (decay ** t)
    return max(eps, end_e)

def main(args):
    import stable_baselines3 as sb3

    if sb3.__version__ < "2.0":
        raise ValueError(
            """Ongoing migration: run the following command to install the new dependencies:

poetry run pip install "stable_baselines3==2.0.0a1"
"""
        )
    
    run_name = f"{args.env_id}__{args.exp_name}__{args.seed}__{int(time.time())}"
    if args.track:
        import wandb

        wandb.init(
            project=args.wandb_project_name,
            entity=args.wandb_entity,
            sync_tensorboard=True,
            config=vars(args),
            name=run_name,
            monitor_gym=True,
            save_code=True,
        )
    writer = SummaryWriter(f"runs/{run_name}")
    writer.add_text(
        "hyperparameters",
        "|param|value|\n|-|-|\n%s" % ("\n".join([f"|{key}|{value}|" for key, value in vars(args).items()])),
    )

    # TRY NOT TO MODIFY: seeding
    random.seed(args.seed)
    np.random.seed(args.seed)
    key = jax.random.PRNGKey(args.seed)
    key, q_key = jax.random.split(key, 2)

    # env setup
    envs = gym.vector.SyncVectorEnv(
        [make_env(args.env_id, args.seed + i, i, args.capture_video, run_name) for i in range(args.num_envs)]
    )
    assert isinstance(envs.single_action_space, gym.spaces.Discrete), "only discrete action space is supported"

    obs, _ = envs.reset(seed=args.seed)

    if args.architecture == 'BASELINE':
        q_network = QNetwork(action_dim=envs.single_action_space.n)
    elif args.architecture == 'DSOM':
        q_network = DSOM(action_dim=envs.single_action_space.n, obs_dim=obs.shape[-1])
        q_network.lr = args.dsom_lr
        q_network.elasticity = args.elasticity
    elif args.architecture == 'SDM':
        q_network = SDM(action_dim=envs.single_action_space.n, obs_dim=obs.shape[-1])

    q_state = TrainState.create(
        apply_fn=q_network.apply,
        params=q_network.init(q_key, obs).unfreeze(),
        target_params=q_network.init(q_key, obs).unfreeze(),
        tx=optax.adam(learning_rate=args.learning_rate), # TODO: add other optimizers here
    )

    if args.plot_som > 0:
        all_obs = np.empty((0,8), dtype=float)
        plot_codebook_vecs(q_state.params['params']['som_codebook_vecs'], 0, all_obs)

    q_network.apply = jax.jit(q_network.apply)
    # This step is not necessary as init called on same observation and key will always lead to same initializations
    q_state = q_state.replace(target_params=optax.incremental_update(q_state.params, q_state.target_params, 1))

    rb = ReplayBuffer(
        args.buffer_size,
        envs.single_observation_space,
        envs.single_action_space,
        "cpu",
        handle_timeout_termination=False,
    )

    # TODO: this needs to be adjusted to use SARSA as well as QLEARNING
    @jax.jit
    def update(q_state, observations, actions, next_observations, rewards, dones):
        if args.architecture == 'DSOM':
            q_state.params['params']['som_codebook_vecs'] = q_network.dsom_update(q_state.params, observations)

        q_next_target = q_network.apply(q_state.target_params, next_observations)  # (batch_size, num_actions)
        q_next_target = jnp.max(q_next_target, axis=-1)  # (batch_size,)
        next_q_value = rewards + (1 - dones) * args.gamma * q_next_target

        def mse_loss(params):
            q_pred = q_network.apply(params, observations)  # (batch_size, num_actions)
            q_pred = q_pred[jnp.arange(q_pred.shape[0]), actions.squeeze()]  # (batch_size,)
            return ((q_pred - next_q_value) ** 2).mean(), q_pred

        (loss_value, q_pred), grads = jax.value_and_grad(mse_loss, has_aux=True)(q_state.params)
        q_state = q_state.apply_gradients(grads=grads)

        if args.architecture == 'SDM':
            (sdm_keys, sdm_values) = q_network.sdm_update(q_state.params)
            q_state.params['params']['sdm_keys'] = sdm_keys
            q_state.params['params']['sdm_values'] = sdm_values

        return loss_value, q_pred, q_state

    start_time = time.time()

    # TRY NOT TO MODIFY: start the game
    obs, _ = envs.reset(seed=args.seed)
    num_episodes = 0
    for global_step in range(args.total_timesteps):
        # TODO: would need to alter this from epsilon-greedy for SARSA implementation 
        # ALGO LOGIC: put action logic here
        if args.eps_scheduler == 'LINEAR':
            epsilon = linear_schedule(args.start_e, args.end_e, args.exploration_fraction * args.total_timesteps, global_step)
        elif args.eps_scheduler == 'EXPONENTIAL':
            epsilon = exponential_schedule(args.start_e, args.end_e, args.eps_decay, num_episodes)
        else:
            raise Exception
        
        if random.random() < epsilon:
            actions = np.array([envs.single_action_space.sample() for _ in range(envs.num_envs)])
        else:
            q_values = q_network.apply(q_state.params, obs)
            actions = q_values.argmax(axis=-1)
            actions = jax.device_get(actions)

        # TRY NOT TO MODIFY: execute the game and log data.
        next_obs, rewards, terminated, truncated, infos = envs.step(actions)

        # TRY NOT TO MODIFY: record rewards for plotting purposes
        if "final_info" in infos:
            for info in infos["final_info"]:
                num_episodes += 1

                # Skip the envs that are not done
                if "episode" not in info:
                    continue
                print(f"global_step={global_step}, episodic_return={info['episode']['r']}")
                writer.add_scalar("charts/episodic_return", info["episode"]["r"], num_episodes)
                writer.add_scalar("charts/episodic_length", info["episode"]["l"], num_episodes)
                writer.add_scalar("charts/epsilon", epsilon, num_episodes)

        # TRY NOT TO MODIFY: save data to reply buffer; handle `final_observation`
        real_next_obs = next_obs.copy()
        for idx, d in enumerate(truncated):
            if d:
                real_next_obs[idx] = infos["final_observation"][idx]
        rb.add(obs, real_next_obs, actions, rewards, terminated, infos)

        # TRY NOT TO MODIFY: CRUCIAL step easy to overlook
        obs = next_obs

        # ALGO LOGIC: training.
        if global_step > args.learning_starts:
            if global_step % args.train_frequency == 0:
                # TODO: does making the replay buffer size 1 effectively turn it off?
                data = rb.sample(args.batch_size)
                # perform a gradient-descent step
                q_network.k = epsilon
                loss, old_val, q_state = update(
                    q_state,
                    data.observations.numpy(),
                    data.actions.numpy(),
                    data.next_observations.numpy(),
                    data.rewards.flatten().numpy(),
                    data.dones.flatten().numpy(),
                )

                if args.plot_som > 0:
                    all_obs = np.append(all_obs, data.observations.numpy(), axis=0)

                if global_step % 100 == 0:
                    writer.add_scalar("losses/td_loss", jax.device_get(loss), global_step)
                    writer.add_scalar("losses/q_values", jax.device_get(old_val).mean(), global_step)
                    print("SPS:", int(global_step / (time.time() - start_time))) # steps per second
                    writer.add_scalar("charts/SPS", int(global_step / (time.time() - start_time)), global_step)
                    
                if args.plot_som > 0 and global_step % args.plot_som == 0:
                    plot_codebook_vecs(q_state.params['params']['som_codebook_vecs'], global_step, all_obs)
                    all_obs = np.empty((0,8), dtype=float)

            # update target network
            if global_step % args.target_network_frequency == 0:
                q_state = q_state.replace(
                    target_params=optax.incremental_update(q_state.params, q_state.target_params, args.tau)
                )

    if args.save_model:
        model_path = f"runs/{run_name}/{args.exp_name}.cleanrl_model"
        with open(model_path, "wb") as f:
            f.write(flax.serialization.to_bytes(q_state.params))
        print(f"model saved to {model_path}")
        from cleanrl_utils.evals.dqn_jax_eval import evaluate

        episodic_returns = evaluate(
            model_path,
            make_env,
            args.env_id,
            eval_episodes=10,
            run_name=f"{run_name}-eval",
            Model=QNetwork,
            epsilon=0.05,
        )
        for idx, episodic_return in enumerate(episodic_returns):
            writer.add_scalar("eval/episodic_return", episodic_return, idx)

        if args.upload_model:
            from cleanrl_utils.huggingface import push_to_hub

            repo_name = f"{args.env_id}-{args.exp_name}-seed{args.seed}"
            repo_id = f"{args.hf_entity}/{repo_name}" if args.hf_entity else repo_name
            push_to_hub(args, episodic_returns, repo_id, "DQN", f"runs/{run_name}", f"videos/{run_name}-eval")

    envs.close()
    writer.close()


if __name__ == "__main__":
    args = parse_args()
    main(args)