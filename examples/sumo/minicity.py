"""Example of modified minicity network with human-driven vehicles."""
from flow.controllers import IDMController
from flow.controllers import RLController
from flow.core.experiment import SumoExperiment
from flow.core.params import SumoParams, EnvParams, NetParams, InitialConfig, InFlows, SumoCarFollowingParams
from flow.core.vehicles import Vehicles
from flow.envs.loop.loop_accel import AccelEnv, ADDITIONAL_ENV_PARAMS
from flow.scenarios.minicity import MiniCityScenario, ADDITIONAL_NET_PARAMS
from flow.controllers.routing_controllers import MinicityRouter
from flow.core.traffic_lights import TrafficLights
import numpy as np

np.random.seed(204)


def minicity_example(render=None,
                     save_render=None,
                     sight_radius=None,
                     pxpm=None,
                     show_radius=None):
    """
    Perform a simulation of vehicles on modified minicity of University of
    Delaware.

    Parameters
    ----------
    render: bool, optional
        specifies whether to use sumo's gui during execution

    Returns
    -------
    exp: flow.core.SumoExperiment type
        A non-rl experiment demonstrating the performance of human-driven
        vehicles on the minicity scenario.
    """
    sumo_params = SumoParams(render=False)

    if render is not None:
        sumo_params.render = render

    if save_render is not None:
        sumo_params.save_render = save_render

    if sight_radius is not None:
        sumo_params.sight_radius = sight_radius

    if pxpm is not None:
        sumo_params.pxpm = pxpm

    if show_radius is not None:
        sumo_params.show_radius = show_radius

    vehicles = Vehicles()
    vehicles.add(
        veh_id="idm",
        acceleration_controller=(IDMController, {}),
        routing_controller=(MinicityRouter, {}),
        speed_mode="right_of_way",
        lane_change_mode="no_lat_collide",
        initial_speed=0,
        num_vehicles=100)
    vehicles.add(
        veh_id="rl",
        acceleration_controller=(RLController, {}),
        routing_controller=(MinicityRouter, {}),
        speed_mode="right_of_way",
        initial_speed=0,
        num_vehicles=10)

    tl_logic = TrafficLights(baseline=False)

    # nodes = ["n_i3", "n_i1", "n_i4"]
    nodes = ["n_i1", 'n_i3', "n_i4", 'n_i6', 'n_i8']
    phases = [{"duration": "20", "state": "GGGGrrGGGGrr"},
              {"duration": "4", "state": "yyyGrryyGyrr"},
              {"duration": "20", "state": "GrrGGGGrrGGG"},
              {"duration": "4", "state": "GrryyyGrryyy"}]

    phases_3 = [{"duration": "20", "state": "GGGGGrrrGGGGGrrr"},
                {"duration": "4", "state": "yyyyyrrryyyyyrrr"},
                {"duration": "20", "state": "GrrrGGGGGrrrGGGG"},
                {"duration": "4", "state": "yrrryyyyyrrryyyy"}]

    phases_6 = [{"duration": "20", "state": "GGGGGrr"},
                {"duration": "4", "state": "yyGGGrr"},
                {"duration": "20", "state": "GrrrGGG"},
                {"duration": "4", "state": "Grrryyy"}]

    phases_8 = [{"duration": "20", "state": "GrrrGGG"},
                {"duration": "4", "state": "Grrryyy"},
                {"duration": "20", "state": "GGGGGrr"},
                {"duration": "4", "state": "yyGGGrr"}]

    # {"duration": "15", "state": "rrrrrrrrrGGG"},
    # {"duration": "3", "state": "rrrrrrrrryyy"}]

    for node_id in nodes:
        print(node_id)
        if node_id == 'n_i3':
            tl_logic.add(node_id, phases=phases_3,
                         tls_type="actuated", programID=1)
        elif node_id == 'n_i6':
            tl_logic.add(node_id, phases=phases_6,
                         tls_type="actuated", programID=1)
        elif node_id == 'n_i8':
            tl_logic.add(node_id, phases=phases_8,
                         tls_type="actuated", programID=1)
        else:
            tl_logic.add(node_id, phases=phases,
                         tls_type="actuated", programID=1)

    env_params = EnvParams(additional_params=ADDITIONAL_ENV_PARAMS)

    additional_net_params = ADDITIONAL_NET_PARAMS.copy()

    additional_net_params['traffic_lights'] = True
    net_params = NetParams(
        no_internal_links=False, additional_params=additional_net_params)

    initial_config = InitialConfig(
        spacing="random",
        min_gap=5
    )
    scenario = MiniCityScenario(
        name="minicity",
        vehicles=vehicles,
        initial_config=initial_config,
        net_params=net_params,
        traffic_lights=tl_logic)

    env = AccelEnv(env_params, sumo_params, scenario)

    return SumoExperiment(env, scenario)


if __name__ == "__main__":
    # import the experiment variable
    # There are six modes of pyglet rendering:
    # No rendering: minicity_example(render=False)
    # SUMO-GUI rendering: minicity_example(render=True)
    # Static grayscale rendering: minicity_example(render="gray")
    # Dynamic grayscale rendering: minicity_example(render="dgray")
    # Static RGB rendering: minicity_example(render="rgb")
    # Dynamic RGB rendering: minicity_example(render="drgb")
    exp = minicity_example(render=True,
                           save_render=False,
                           sight_radius=50,
                           pxpm=3,
                           show_radius=False)

    # run for a set number of rollouts / time steps
    exp.run(1, 7500)
