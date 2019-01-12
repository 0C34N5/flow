"""Environment for training the acceleration behavior of vehicles in a loop."""

from flow.envs.base_env import Env
from flow.core import rewards
from flow.core.params import InitialConfig, NetParams, SumoCarFollowingParams
from flow.controllers import IDMController

from gym.spaces.box import Box
from gym.spaces.tuple_space import Tuple

import numpy as np

import os
from os.path import expanduser
HOME = expanduser("~")
import time

ADDITIONAL_ENV_PARAMS = {
    # maximum acceleration for autonomous vehicles, in m/s^2
    "max_accel": 3,
    # maximum deceleration for autonomous vehicles, in m/s^2
    "max_decel": 5,
    # desired velocity for all vehicles in the network, in m/s
    "target_velocity": 11.176,
    # reward function performance-consumption tradeoff
    "alpha": 0.8,
    # reward function safety-navigation tradeoff
    "beta": 0.5,
}


class SoftIntersectionEnv(Env):
    def __init__(self, env_params, sumo_params, scenario):
        print("Starting SoftIntersectionEnv...")
        for p in ADDITIONAL_ENV_PARAMS.keys():
            if p not in env_params.additional_params:
                raise KeyError(
                    'Environment parameter "{}" not supplied'.format(p))

        super().__init__(env_params, sumo_params, scenario)

        # setup traffic lights
        self.tls_id = self.traci_connection.trafficlight.getIDList()[0]
        self.tls_state =\
            self.traci_connection.trafficlight.\
            getRedYellowGreenState(self.tls_id)
        self.tls_definition =\
            self.traci_connection.trafficlight.\
            getCompleteRedYellowGreenDefinition(self.tls_id)
        self.tls_phase = 0
        self.tls_phase_count = 0
        for logic in self.tls_definition:
            for phase in logic._phases:
                self.tls_phase_count += 1

        # setup speed broadcasters
        self.sbc_locations = [
            "e_1_sbc+_0", "e_1_sbc+_1",  # east bound
            "e_3_sbc+_0", "e_3_sbc+_1",  # south bound
            "e_5_sbc+_0", "e_5_sbc+_1",  # west bound
            "e_7_sbc+_0", "e_7_sbc+_1",  # north bound
        ]
        # default speed reference to 11.176 m/s
        self.sbc_reference = {
            loc: self.traci_connection.lane.getMaxSpeed(loc)
            for loc in self.sbc_locations
        }

        # setup inflow outflow logger
        self.inflow_locations = [
            "e_1_sbc+_0", "e_1_sbc+_1",  # east bound
            "e_3_sbc+_0", "e_3_sbc+_1",  # south bound
            "e_5_sbc+_0", "e_5_sbc+_1",  # west bound
            "e_7_sbc+_0", "e_7_sbc+_1",  # north bound
        ]
        self.inflow_accelerations = {loc: 0 for loc in self.inflow_locations}
        self.inflow_speeds = {loc: 0 for loc in self.inflow_locations}
        self.inflow_densities = { loc: 0 for loc in self.inflow_locations}
        self.inflow_fuels = {loc: 0 for loc in self.inflow_locations}
        self.inflow_co2s = {loc: 0 for loc in self.inflow_locations}
        self.outflow_locations = [
            "e_2_sbc-_0", "e_2_sbc-_1",  # east bound
            "e_4_sbc-_0", "e_4_sbc-_1",  # south bound
            "e_6_sbc-_0", "e_6_sbc-_1",  # west bound
            "e_8_sbc-_0", "e_8_sbc-_1",  # north bound
        ]
        self.outflow_accelerations = {loc: 0 for loc in self.outflow_locations}
        self.outflow_speeds = {loc: 0 for loc in self.outflow_locations}
        self.outflow_densities = {loc: 0 for loc in self.outflow_locations}
        self.outflow_fuels = {loc: 0 for loc in self.outflow_locations}
        self.outflow_co2s = {loc: 0 for loc in self.outflow_locations}

        # setup reward-related variables
        self.alpha = env_params.additional_params["alpha"]
        self.rewards = 0

    # ACTION GOES HERE
    @property
    def action_space(self):
        return Box(
            low=0,
            high=max(self.scenario.max_speed, 1),
            shape=(9,),
            dtype=np.float32)

    def set_action(self, action):
        if self.time_counter % 10 == 0:
            self.sbc_reference = {
                loc: np.clip(action[idx], 0, np.inf)
                for idx, loc in enumerate(self.sbc_locations)
            }
            self.tls_phase_increment = np.clip(
                int(action[-1]), 0, 1)
        self._set_reference(self.sbc_reference)
        self._set_phase(self.tls_phase + self.tls_phase_increment)

    # OBSERVATION GOES HERE
    @property
    def observation_space(self):
        """See class definition."""
        return Box(
            low=0.,
            high=np.inf,
            shape=(49,),
            dtype=np.float32)

    def get_observation(self, **kwargs):
        inflow_accelerations = [
            self.inflow_accelerations[loc]
            for loc in self.inflow_locations
        ]
        inflow_speeds = [
            self.inflow_speeds[loc]
            for loc in self.inflow_locations
        ]
        inflow_densities = [
            self.inflow_densities[loc]
            for loc in self.inflow_locations
        ]
        outflow_accelerations = [
            self.outflow_accelerations[loc]
            for loc in self.outflow_locations
        ]
        outflow_speeds = [
            self.outflow_speeds[loc]
            for loc in self.outflow_locations
        ]
        outflow_densities = [
            self.outflow_densities[loc]
            for loc in self.outflow_locations
        ]
        tls_phase = self.tls_phase
        observation = np.asarray(
            inflow_accelerations + inflow_speeds + inflow_densities +
            outflow_accelerations + outflow_speeds + outflow_densities +
            [tls_phase]
        )
        return observation

    # REWARD FUNCTION GOES HERE
    def get_reward(self, **kwargs):
        speeds = list(self.inflow_speeds.values())
        densities = list(self.inflow_densities.values())
        performance = 0.4*np.mean(speeds) + 0.1*-np.std(speeds) + \
                      0.4*-np.mean(densities) + 0.1*-np.std(densities)
        fuels = list(self.inflow_fuels.values())
        co2s = list(self.inflow_co2s.values())
        consumption = 0.5*-np.mean(fuels) + 0.5*-np.mean(co2s)
        return self.alpha * performance + (1 - self.alpha) * consumption

    def get_reward_deprecated(self, **kwargs):
        _inflow = np.asarray([
            self.inflow_values[loc]
            for loc in self.inflow_locations
        ])
        _outflow = np.asarray([
            self.outflow_values[loc]
            for loc in self.outflow_locations
        ])
        input_efficiency = \
            self.alpha*np.mean(_inflow) + (1 - self.alpha)*(-np.std(_inflow))
        output_efficiency = \
            self.alpha*np.mean(_outflow) + (1 - self.alpha)*(-np.std(_outflow))
        return input_efficiency + output_efficiency

    # UTILITY FUNCTION GOES HERE
    def additional_command(self):
        # update inflow statistics
        inflow_stats = []
        for idx, loc in enumerate(self.inflow_locations):
            flow_stats = self.get_flow_stats(loc)
            inflow_stats.append(flow_stats)
            acceleration, speed, _, _, density, fuel, co2 = flow_stats
            self.inflow_accelerations[loc] = acceleration
            self.inflow_speeds[loc] = speed
            self.inflow_densities[loc] = density
            self.inflow_fuels[loc] = fuel
            self.inflow_co2s[loc] = co2

        # update outflow statistics
        outflow_stats = []
        for idx, loc in enumerate(self.outflow_locations):
            flow_stats = self.get_flow_stats(loc)
            outflow_stats.append(flow_stats)
            acceleration, speed, _, _, density, fuel, co2 = flow_stats
            self.outflow_accelerations[loc] = acceleration
            self.outflow_speeds[loc] = speed
            self.outflow_densities[loc] = density
            self.outflow_fuels[loc] = fuel
            self.outflow_co2s[loc] = co2

        # update traffic lights state
        self.tls_state =\
            self.traci_connection.trafficlight.\
            getRedYellowGreenState(self.tls_id)

        # disable skip to test traci tls and sbc setter methods
        self.test_sbc(skip=True)
        self.test_tls(skip=True)
        self.test_ioflow(inflow_stats, outflow_stats, skip=True)
        self.test_reward(skip=True)

    def test_sbc(self, skip=True):
        if self.time_counter > 50 and not skip:
            print("Broadcasting reference...")
            self.sbc_reference = {
                loc: 1
                for loc in self.sbc_locations
            }
            self._set_reference(self.sbc_reference)

    def test_tls(self, skip=True):
        if self.time_counter % 10 == 0 and not skip:
            print("Switching phase...")
            self.tls_phase = np.random.randint(0, self.tls_phase_count-1)
            print("New phase:", self.tls_phase)
            self._set_phase(self.tls_phase)

    def test_ioflow(self, inflow_stats, outflow_stats, skip=False):
        if not skip:
            print(inflow_stats)
            print(self.inflow_values)
            print(outflow_stats)
            print(self.outflow_values)

    def test_reward(self, skip=True):
        if not skip:
            _reward = self.get_reward()
            print('Reward this step:', _reward)
            self.rewards += _reward
            print('Total rewards:', self.rewards)

    def get_flow_stats(self, loc):
        speed = self.traci_connection.lane.getLastStepMeanSpeed(loc)
        acceleration = (speed - self.inflow_speeds[loc])/self.sim_step
        count = self.traci_connection.lane.getLastStepVehicleNumber(loc)
        length = self.traci_connection.lane.getLength(loc)
        density = count / length
        fuel = self.traci_connection.lane.getFuelConsumption(loc)
        co2 = self.traci_connection.lane.getCO2Emission(loc)
        return [acceleration, speed, count, length, density, fuel, co2]

    def _set_reference(self, sbc_reference):
        for sbc, reference in sbc_reference.items():
            sbc_clients = self.traci_connection.lane.getLastStepVehicleIDs(sbc)
            for veh_id in sbc_clients:
                self.traci_connection.vehicle.setMaxSpeed(veh_id, reference)

    def _set_phase(self, tls_phase):
        self.traci_connection.trafficlight.setPhase(\
            self.tls_id, tls_phase)

    # DO NOT WORRY ABOUT ANYTHING BELOW THIS LINE >◡<
    def _apply_rl_actions(self, rl_actions):
        self.set_action(rl_actions)

    def get_state(self, **kwargs):
        return self.get_observation(**kwargs)

    def compute_reward(self, actions, **kwargs):
        return self.get_reward(**kwargs)

class HardIntersectionEnv(Env):
    def __init__(self, env_params, sumo_params, scenario):
        print("Starting HardIntersectionEnv...")
        for p in ADDITIONAL_ENV_PARAMS.keys():
            if p not in env_params.additional_params:
                raise KeyError(
                    'Environment parameter "{}" not supplied'.format(p))

        super().__init__(env_params, sumo_params, scenario)

        # setup traffic lights
        self.tls_id = self.traci_connection.trafficlight.getIDList()[0]
        self.tls_state =\
            self.traci_connection.trafficlight.\
            getRedYellowGreenState(self.tls_id)
        self.tls_definition =\
            self.traci_connection.trafficlight.\
            getCompleteRedYellowGreenDefinition(self.tls_id)
        self.tls_phase = 0
        self.tls_phase_count = 0
        for logic in self.tls_definition:
            for phase in logic._phases:
                self.tls_phase_count += 1

        # setup speed broadcasters
        self.sbc_locations = [
            "e_1_zone1>_0", "e_1_zone1>_1",  # east bound
            "e_1_zone2>_0", "e_1_zone2>_1",  # east bound
            "e_1_zone3>_0", "e_1_zone3>_1",  # east bound
            "e_1_zone4>_0", "e_1_zone4>_1",  # east bound

            "e_2_zone1>_0", "e_2_zone1>_1",  # south bound
            "e_2_zone2>_0", "e_2_zone2>_1",  # south bound
            "e_2_zone3>_0", "e_2_zone3>_1",  # south bound
            "e_2_zone4>_0", "e_2_zone4>_1",  # south bound

            "e_3_zone1>_0", "e_3_zone1>_1",  # west bound
            "e_3_zone2>_0", "e_3_zone2>_1",  # west bound
            "e_3_zone3>_0", "e_3_zone3>_1",  # west bound
            "e_3_zone4>_0", "e_3_zone4>_1",  # west bound

            "e_4_zone1>_0", "e_4_zone1>_1",  # north bound
            "e_4_zone2>_0", "e_4_zone2>_1",  # north bound
            "e_4_zone3>_0", "e_4_zone3>_1",  # north bound
            "e_4_zone4>_0", "e_4_zone4>_1",  # north bound
        ]
        # default speed reference to 11.176 m/s
        self.sbc_command = {
            loc: self.traci_connection.lane.getMaxSpeed(loc)
            for loc in self.sbc_locations
        }

        # setup inflow outflow logger
        self.inflow_locations = [
            "e_1_zone1>_0", "e_1_zone1>_1",  # east bound
            "e_1_zone2>_0", "e_1_zone2>_1",  # east bound
            "e_1_zone3>_0", "e_1_zone3>_1",  # east bound
            "e_1_zone4>_0", "e_1_zone4>_1",  # east bound

            "e_2_zone1>_0", "e_2_zone1>_1",  # south bound
            "e_2_zone2>_0", "e_2_zone2>_1",  # south bound
            "e_2_zone3>_0", "e_2_zone3>_1",  # south bound
            "e_2_zone4>_0", "e_2_zone4>_1",  # south bound

            "e_3_zone1>_0", "e_3_zone1>_1",  # west bound
            "e_3_zone2>_0", "e_3_zone2>_1",  # west bound
            "e_3_zone3>_0", "e_3_zone3>_1",  # west bound
            "e_3_zone4>_0", "e_3_zone4>_1",  # west bound

            "e_4_zone1>_0", "e_4_zone1>_1",  # north bound
            "e_4_zone2>_0", "e_4_zone2>_1",  # north bound
            "e_4_zone3>_0", "e_4_zone3>_1",  # north bound
            "e_4_zone4>_0", "e_4_zone4>_1",  # north bound
        ]
        self.inflow_accelerations = {loc: 0 for loc in self.inflow_locations}
        self.inflow_speeds = {loc: 0 for loc in self.inflow_locations}
        self.inflow_densities = { loc: 0 for loc in self.inflow_locations}
        self.inflow_collisions = { loc: 0 for loc in self.inflow_locations}
        self.inflow_fuels = {loc: 0 for loc in self.inflow_locations}
        self.inflow_co2s = {loc: 0 for loc in self.inflow_locations}
        self.outflow_locations = [
            "e_1_zone1<_0", "e_1_zone1<_1",  # east bound
            "e_1_zone2<_0", "e_1_zone2<_1",  # east bound
            "e_1_zone3<_0", "e_1_zone3<_1",  # east bound
            "e_1_zone4<_0", "e_1_zone4<_1",  # east bound

            "e_2_zone1<_0", "e_2_zone1<_1",  # south bound
            "e_2_zone2<_0", "e_2_zone2<_1",  # south bound
            "e_2_zone3<_0", "e_2_zone3<_1",  # south bound
            "e_2_zone4<_0", "e_2_zone4<_1",  # south bound

            "e_3_zone1<_0", "e_3_zone1<_1",  # west bound
            "e_3_zone2<_0", "e_3_zone2<_1",  # west bound
            "e_3_zone3<_0", "e_3_zone3<_1",  # west bound
            "e_3_zone4<_0", "e_3_zone4<_1",  # west bound

            "e_4_zone1<_0", "e_4_zone1<_1",  # north bound
            "e_4_zone2<_0", "e_4_zone2<_1",  # north bound
            "e_4_zone3<_0", "e_4_zone3<_1",  # north bound
            "e_4_zone4<_0", "e_4_zone4<_1",  # north bound
        ]
        self.outflow_accelerations = {loc: 0 for loc in self.outflow_locations}
        self.outflow_speeds = {loc: 0 for loc in self.outflow_locations}
        self.outflow_densities = {loc: 0 for loc in self.outflow_locations}
        self.outflow_collisions = {loc: 0 for loc in self.outflow_locations}
        self.outflow_fuels = {loc: 0 for loc in self.outflow_locations}
        self.outflow_co2s = {loc: 0 for loc in self.outflow_locations}

        # setup collision tracker
        self.collision_count = 0

        # setup reward-related variables
        self.alpha = env_params.additional_params["alpha"]
        self.beta = env_params.additional_params["beta"]
        self.rewards = 0

    # ACTION GOES HERE
    @property
    def action_space(self):
        return Box(
            low=0,
            high=max(self.scenario.max_speed, self.tls_phase_count),
            shape=(9,),
            dtype=np.float32)

    def set_action(self, action):
        self.sbc_command = {
            loc: np.clip(action[idx], 0, np.inf)
            for idx, loc in enumerate(self.sbc_locations)
        }
        self.tls_phase_increment = np.clip(
            int(action[-1]), 0, self.tls_phase_count)
        self._set_command(self.sbc_command)
        self._set_phase(
            (self.tls_phase + self.tls_phase_increment) % self.tls_phase_count)

    # OBSERVATION GOES HERE
    @property
    def observation_space(self):
        """See class definition."""
        return Box(
            low=0.,
            high=np.inf,
            shape=(65,),
            dtype=np.float32)

    def get_observation(self, **kwargs):
        inflow_accelerations = [
            self.inflow_accelerations[loc]
            for loc in self.inflow_locations
        ]
        inflow_speeds = [
            self.inflow_speeds[loc]
            for loc in self.inflow_locations
        ]
        inflow_densities = [
            self.inflow_densities[loc]
            for loc in self.inflow_locations
        ]
        inflow_collisions = [
            self.inflow_collisions[loc]
            for loc in self.inflow_locations
        ]
        outflow_accelerations = [
            self.outflow_accelerations[loc]
            for loc in self.outflow_locations
        ]
        outflow_speeds = [
            self.outflow_speeds[loc]
            for loc in self.outflow_locations
        ]
        outflow_densities = [
            self.outflow_densities[loc]
            for loc in self.outflow_locations
        ]
        outflow_collisions = [
            self.outflow_collisions[loc]
            for loc in self.outflow_locations
        ]
        tls_phase = self.tls_phase
        observation = np.asarray(
            inflow_accelerations + inflow_speeds +
            inflow_densities + inflow_collisions +
            outflow_accelerations + outflow_speeds +
            outflow_densities + outflow_collisions +
            [tls_phase]
        )
        return observation

    # REWARD FUNCTION GOES HERE
    def get_reward(self, **kwargs):
        speeds = list(self.inflow_speeds.values())
        densities = list(self.inflow_densities.values())
        performance = 0.4*np.mean(speeds) + 0.1*-np.std(speeds) + \
                      0.4*-np.mean(densities) + 0.1*-np.std(densities)
        fuels = list(self.inflow_fuels.values())
        co2s = list(self.inflow_co2s.values())
        consumption = 0.5*-np.mean(fuels) + 0.5*-np.mean(co2s)
        navigation = self.alpha * performance + (1 - self.alpha) * consumption
        safety = self.collision_count * 100
        return self.beta * safety + (1 - self.bata) * navigation

    # UTILITY FUNCTION GOES HERE
    def additional_command(self):
        # update inflow statistics
        inflow_stats = []
        for idx, loc in enumerate(self.inflow_locations):
            flow_stats = self.get_flow_stats(loc)
            inflow_stats.append(flow_stats)
            acceleration, speed, _, _, density, collision, fuel, co2 = \
                flow_stats
            self.inflow_accelerations[loc] = acceleration
            self.inflow_speeds[loc] = speed
            self.inflow_densities[loc] = density
            self.inflow_collisions[loc] = collision
            self.inflow_fuels[loc] = fuel
            self.inflow_co2s[loc] = co2

        # update outflow statistics
        outflow_stats = []
        for idx, loc in enumerate(self.outflow_locations):
            flow_stats = self.get_flow_stats(loc)
            outflow_stats.append(flow_stats)
            acceleration, speed, _, _, density, collision, fuel, co2 = \
                flow_stats
            self.outflow_accelerations[loc] = acceleration
            self.outflow_speeds[loc] = speed
            self.outflow_densities[loc] = density
            self.outflow_collisions[loc] = collision
            self.outflow_fuels[loc] = fuel
            self.outflow_co2s[loc] = co2

        # update traffic lights state
        self.tls_state =\
            self.traci_connection.trafficlight.\
            getRedYellowGreenState(self.tls_id)

        # update collision counter
        self.collision_count = \
            self.traci_connection.simulation.getCollidingVehiclesNumber()
        self.collision_vehicles = \
            self.traci_connection.simulation.getStopEndingVehiclesIDList()

        # disable skip to test traci tls and sbc setter methods
        self.test_sbc(skip=True)
        self.test_tls(skip=True)
        self.test_ioflow(inflow_stats, outflow_stats, skip=True)
        self.test_reward(skip=True)

    def test_sbc(self, skip=True):
        if self.time_counter > 50 and not skip:
            print("Broadcasting reference...")
            self.sbc_command = {
                loc: 1
                for loc in self.sbc_locations
            }
            self._set_command(self.sbc_command)

    def get_flow_stats(self, loc):
        speed = self.traci_connection.lane.getLastStepMeanSpeed(loc)
        acceleration = (speed - self.inflow_speeds[loc])/self.sim_step
        count = self.traci_connection.lane.getLastStepVehicleNumber(loc)
        length = self.traci_connection.lane.getLength(loc)
        lane_vehicles = self.traci_connection.lane.getLastStepVehicleIDs(loc)
        collision = \
            len(set(lane_vehicles).intersection(self.collision_vehicles))
        density = count / length
        fuel = self.traci_connection.lane.getFuelConsumption(loc)
        co2 = self.traci_connection.lane.getCO2Emission(loc)
        return [
            acceleration, speed, count, length, density, collision, fuel, co2
        ]

    def _set_command(self, sbc_command):
        for sbc, reference in sbc_command.items():
            sbc_clients = self.traci_connection.lane.getLastStepVehicleIDs(sbc)
            for veh_id in sbc_clients:
                self.traci_connection.vehicle.setSpeed(veh_id, reference)
