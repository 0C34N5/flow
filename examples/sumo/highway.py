"""
Example of a multi-lane network with human-driven vehicles.
"""
import logging

from flow.controllers.car_following_models import IDMController
from flow.controllers.lane_change_controllers import StaticLaneChanger
from flow.controllers.routing_controllers import ContinuousRouter
from flow.core.experiment import SumoExperiment
from flow.core.params import SumoParams, EnvParams, \
    NetParams, InitialConfig, InFlows
from flow.core.vehicles import Vehicles
from flow.envs.loop.loop_accel import AccelEnv, ADDITIONAL_ENV_PARAMS
from flow.scenarios.highway.gen import HighwayGenerator
from flow.scenarios.highway.scenario import HighwayScenario, \
    ADDITIONAL_NET_PARAMS


def highway_example(sumo_binary=None):
    logging.basicConfig(level=logging.INFO)

    sumo_params = SumoParams(sumo_binary="sumo-gui")

    if sumo_binary is not None:
        sumo_params.sumo_binary = sumo_binary

    vehicles = Vehicles()
    vehicles.add(veh_id="human",
                 acceleration_controller=(IDMController, {}),
                 lane_change_controller=(StaticLaneChanger, {}),
                 routing_controller=(ContinuousRouter, {}),
                 initial_speed=0,
                 num_vehicles=20)
    vehicles.add(veh_id="human2",
                 acceleration_controller=(IDMController, {}),
                 lane_change_controller=(StaticLaneChanger, {}),
                 routing_controller=(ContinuousRouter, {}),
                 initial_speed=0,
                 num_vehicles=20)

    env_params = EnvParams(additional_params=ADDITIONAL_ENV_PARAMS)

    inflow = InFlows()
    inflow.add(veh_type="human", edge="highway", probability=0.25,
               departLane="free", departSpeed=20)
    inflow.add(veh_type="human2", edge="highway", probability=0.25,
               departLane="free", departSpeed=20)

    additional_net_params = ADDITIONAL_NET_PARAMS.copy()
    net_params = NetParams(in_flows=inflow,
                           additional_params=additional_net_params)

    initial_config = InitialConfig(spacing="random",
                                   lanes_distribution=4,
                                   shuffle=True)

    scenario = HighwayScenario(name="highway",
                               generator_class=HighwayGenerator,
                               vehicles=vehicles,
                               net_params=net_params,
                               initial_config=initial_config)

    env = AccelEnv(env_params, sumo_params, scenario)

    exp = SumoExperiment(env, scenario)

    logging.info("Experiment Set Up complete")

    return exp


if __name__ == "__main__":
    # import the experiment variable
    exp = highway_example()

    # run for a set number of rollouts / time steps
    exp.run(1, 1500)
