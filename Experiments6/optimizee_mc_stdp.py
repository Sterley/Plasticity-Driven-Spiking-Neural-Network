import json
import numpy as np
import os
import pandas as pd
import pathlib
import pickle
import shutil
import subprocess
import time
from collections import namedtuple
from l2l.optimizees.optimizee import Optimizee
import gym
import nest

NeuroEvolutionOptimizeeMCParameters = namedtuple(
    'NeuroEvoOptimizeeMCParameters', ['path', 'seed', 'save_n_generation', 'run_headless', 'load_parameter'])


################################################################

class NestNetwork():
    def __init__(self):
        nest.ResetKernel()
        nest.set_verbosity('M_ERROR')
        nest.SetKernelStatus(
            {
                'resolution': 0.2,
                'rng_seed': 1,
            })
        self.inpt_velocity = None
        self.inpt_position = None
        self.activator_velocity = None
        self.activator_position = None
        self.outpt = None
        self.nodes = None
        self.spike_detector = None
        self.create_nodes()


    def create_nodes(self):
        params = {'t_ref': 1.0}
        self.activator_velocity = nest.Create("dc_generator", 30, params={'amplitude': 40000.}) #40000.
        self.activator_position = nest.Create("dc_generator", 30, params={'amplitude': 40000.})
        self.inpt_velocity = nest.Create('iaf_psc_alpha', 30, params=params)
        self.inpt_position = nest.Create('iaf_psc_alpha', 30, params=params)
        self.nodes = nest.Create('iaf_psc_alpha', 30, params=params)
        self.outpt = nest.Create('iaf_psc_alpha', 3, params=params)
        self.spike_detector = nest.Create('spike_recorder', 3)


    def connect_network(self, weights, plasticity_flags):
        nest.CopyModel("stdp_synapse", "custom_stdp_synapse", {
            "Wmax": 3000.0,
        })

        nest.Connect(self.activator_velocity, self.inpt_velocity, 'one_to_one')
        nest.Connect(self.activator_position, self.inpt_position, 'one_to_one')

        start_idx = 0
        for (source, target, source_size, target_size, num_conn) in [
            (self.inpt_velocity, self.nodes, 30, 30, 900),
            (self.inpt_position, self.nodes, 30, 30, 900),
            (self.nodes, self.nodes, 30, 30, 900),
            (self.nodes, self.outpt, 30, 3, 90)]:
            weights_tmp = weights[start_idx:start_idx+num_conn].reshape(source_size, target_size)
            plasticity_flags_tmp = plasticity_flags[start_idx:start_idx+num_conn].reshape(source_size, target_size)
            for i in range(len(source)):
                for j in range(len(target)):
                    syn_spec = {
                        "synapse_model": "custom_stdp_synapse" if plasticity_flags_tmp[i, j]>=0 else "static_synapse",
                        "weight": weights_tmp[i, j]
                    }
                    nest.Connect(source[i], target[j], conn_spec={"rule": "all_to_all", "allow_autapses": False}, syn_spec=syn_spec)
            start_idx += num_conn
            
        nest.Connect(self.outpt, self.spike_detector, 'one_to_one')


    def simulate(self, sim_time=20.0):
        nest.Simulate(sim_time)
            
    def feed_network(self, velocity, position):
        velocity_neuron = int(encode_values(-0.07, 0.07, 30, velocity)) - 1
        position_neuron = int(encode_values(-1.2, 0.6, 30, position)) - 1
        nest.SetStatus(self.activator_velocity[velocity_neuron], [{'amplitude':40000.0}])            
        nest.SetStatus(self.activator_position[position_neuron], [{'amplitude':40000.0}])            

    def reset_activators_and_recorders(self):
        for n in range(0, 30):
            nest.SetStatus(self.activator_velocity[n], [{'amplitude':0.0}])            
            nest.SetStatus(self.activator_position[n], [{'amplitude':0.0}])            

        for n in range(0, 3):
            nest.SetStatus(self.spike_detector[n], [{'n_events':0}])            
            nest.SetStatus(self.spike_detector[n], [{'n_events':0}])            

            
    def get_action_from_network(self):
        push_left = nest.GetStatus(self.spike_detector[0], 'n_events')
        push_none = nest.GetStatus(self.spike_detector[1], 'n_events')
        push_right = nest.GetStatus(self.spike_detector[2], 'n_events')
        if (push_left > push_right and push_left > push_none):
            return 0
        elif (push_right > push_left and push_right > push_none):
            return 2
        else:
            return 1

    def set_gym_action(self, action, env):
        observation, reward, done, info = env.step(action) 
        return observation


def encode_values(min_range, max_range, bins, value):
    if max_range == value:
        return bins
    x = np.linspace(min_range, max_range, bins)
    hist, edges = np.histogram(x, bins=bins)
    return np.digitize(value, edges)    

##########################################################################

class NeuroEvolutionOptimizeeMC(Optimizee):
    def __init__(self, traj, parameters):
        super().__init__(traj)
        self.param_path = parameters.path
        self.ind_idx = traj.individual.ind_idx
        self.generation = traj.individual.generation
        self.save_n_generation = parameters.save_n_generation
        self.rng = np.random.default_rng(parameters.seed)
        self.dir_path = ''
        self.fp = pathlib.Path(__file__).parent.absolute()
        self.is_headless = parameters.run_headless
        self.load_parameter = parameters.load_parameter   
        self.min_weight = -20.
        self.max_weight = 20.
        self.min_plasticity_flag = -1
        self.max_plasticity_flag = 1

    def create_individual(self, size_eeo=None, size_eio=None, size_ieo=None, size_iio=None):
        """
        Creates and returns the individual

        Creates the parameters for netlogo.
        The parameter are `weights`, `plasticity_flags`, `plasticity` and `delays`.
        """
        # TODO the creation of the parameters should be more variable
        #  e.g. as parameters or as a config file
        # create random weights
        # create random plasticity_flags
        if self.load_parameter:
            weights, plasticity_flags = self.reload_parameter()
        else:
            weights = self.rng.uniform(self.min_weight, self.max_weight, 2790)
            plasticity_flags = self.rng.uniform(self.min_plasticity_flag, self.max_plasticity_flag, 2790)
        # create individual
        individual = {
            'weights': weights,
            'plasticity_flags': plasticity_flags
        }
        return individual

    def reload_parameter(self):
        randint = self.rng.integers(0, 32, 1)[0]
        if self.load_parameter:
            traj_path = os.path.join(
                self.param_path, 'neuro_evo_test/simulation/trajectories')
            # create a function to split strings via "_" and take 2. argument
            # it also remove the .bin suffix
            def func(x, idx=2): return int(x[:-4].split('_')[idx])
            traj_ids = [func(f) for f in os.listdir(
                traj_path) if f.endswith('.bin')]
            traj_ids = np.sort(np.unique(traj_ids))
            # get the previous last generation idx
            last_gen_idx = traj_ids[-1]
            with open(f'{traj_path}/trajectory_{randint}_{last_gen_idx}.bin',
                      'rb') as tr:
                print(
                    f'loading trajectories {traj_path}/trajectory_{randint}_{last_gen_idx}.bin')
                try:
                    trajectory = pickle.load(tr)
                except ValueError:
                    trajectory = pickle.load(tr)
            weights = trajectory.individual.weights
            plasticity_flags = trajectory.individual.plasticity_flags
        return weights, plasticity_flags


    def simulate(self, traj):
        """
        Simulate a run and return a fitness
        """
        self.ind_idx = traj.individual.ind_idx
        self.generation = traj.individual.generation
        print('Starting with Generation {}'.format(self.generation))

        weights = traj.individual.weights
        plasticity_flags = traj.individual.plasticity_flags
        weights = weights.clip(self.min_weight, self.max_weight)
        plasticity_flags = plasticity_flags.clip(self.min_plasticity_flag, self.max_plasticity_flag)

        self.dir_path = os.path.join(self.param_path,
                                     f'individual_{self.ind_idx}')        
    
        test_weights = weights * 100 
        test_plasticity_flags = plasticity_flags
        #Set same seed for all individuals in the same generation
        """
        Run the MC environment for 110 simulation steps or stop on goal condition
        """
        total_fitness = 0
        for i in range(5):
            test_network = NestNetwork()
            test_network.connect_network(test_weights, test_plasticity_flags)  
            env = gym.make('MountainCar-v0')
            seed_val = self.generation * 1000 + i * 1000
            env.seed(seed_val)
            observation = env.reset()
            position = observation[0]
            velocity = observation[1]   
            max_position = -1.2
            for sim_step in range(0, 1000):
                test_network.reset_activators_and_recorders()
                test_network.feed_network(velocity, position)
                test_network.simulate(20.)
                action = test_network.get_action_from_network() 
                observation = test_network.set_gym_action(action, env)
                position = observation[0]
                velocity = observation[1]     
                if max_position < position:
                    max_position = position
                if position >= 0.5:
                    max_position = position + (100/sim_step)
                    break
            env.close()
            total_fitness += max_position
        fitness = total_fitness/5


        ##################################################################

        if self.generation % self.save_n_generation == 0:
            # create folder if not existent
            result_folder = os.path.join(self.param_path, 'results')
            if not os.path.exists(result_folder):
                os.mkdir(result_folder)
            # rename to individual_GEN_INDEX_results.csv
            results_filename = "individual_{}_{}_result.csv".format(
                self.generation, self.ind_idx)

            individual = {
                'weights': weights,
                'plasticity_flags': plasticity_flags,
                'fitness': fitness
            }            
            df = pd.DataFrame(individual)
            df = df.T
            df.to_csv(os.path.join(result_folder, results_filename),
                      header=False, index=False)               
        return (fitness,) 

    def bounding_func(self, individual):
        individual = {"weights": np.clip(individual['weights'], self.min_weight, self.max_weight),
                      "plasticity_flags": np.clip(individual['plasticity_flags'], self.min_plasticity_flag, self.max_plasticity_flag)}    
        return individual    
    


