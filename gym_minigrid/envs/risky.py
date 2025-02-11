from gym_minigrid.minigrid import *
from gym_minigrid.register import register

# ----------------------------------------
# Rewrite of some aspects of Gym-Minigrid for correect env specification

# String Constants for reward specification
STEP_PENALTY = "step_penalty"
GOAL_REWARD = "goal_reward"
ABSORBING_STATES = "absorbing_states"
ABSORBING_REWARD_GOAL = "absorbing_reward_goal"
ABSORBING_REWARD_LAVA = "absorbing_reward_lava"
SPIKY_TILE_REWARD = "risky_tile_reward"
LAVA_REWARD = "lava_reward"

# Reward specification Dictionary will be passed to the environment
DEFAULT_REWARDS = {
    STEP_PENALTY : 0,
    GOAL_REWARD : 1,
    ABSORBING_STATES : False,
    ABSORBING_REWARD_GOAL : 0,
    ABSORBING_REWARD_LAVA : -1,
    SPIKY_TILE_REWARD : 0,
    LAVA_REWARD : -1
}

class RiskyPathEnv(MiniGridEnv):
    
    # Only actions needed are Move {west, north, east, south}
    class Actions(IntEnum):
        west = 0
        north = 1
        east = 2
        south = 3

    def __init__(
        self,
        width=11,
        height=11,
        show_agent_dir=False,
        agent_start_pos=(2,9),
        goal_positions=[(1,3)],
        lava_positions=None,
        spiky_active=False,
        spiky_positions=None,
        reward_spec=DEFAULT_REWARDS,
        slip_proba=0.,
        wall_rebound=False,
        max_steps=150,
        seed=1337,
    ):
        """Initialize a room surrounded by walls with lava holes and a 
        goal position.

        Args:
            width (int): width of the grid including walls.
            height (int): height of the grid incl. walls.
            show_agent_dir (bool): defines if agent direction is rendered.
            agent_start_pos (tuple): .
            goal_positions (list): List of goal positions.
            lava_positions (list, optional): List of lava positions.
            spiky_active (bool): Whether or not to activate/render spiky_tiles.
            spiky_positions (list, optional): list of spiky_tile positions.
            reward_spec (dict): Defines the reward design.
            slip_proba (float): The probability of agent slipping.
            wall_rebound (bool): Whether walking into walls leads to rebound.
            max_steps (int): max number of steps per episode.
            seed (int): The seed for the environment's RNG.
        """

        # Basic sanity checks
        assert width >= 6 and height >= 6
        assert reward_spec.keys() == DEFAULT_REWARDS.keys()
        assert slip_proba >= 0 and slip_proba < 1, "Must be a probability"
        assert type(agent_start_pos) is tuple, "Must be a x-y-tuple"
        start_x, start_y = agent_start_pos
        assert type(start_x) is int and start_x > 1 and start_x < width - 1
        assert type(start_y) is int and start_y > 1 and start_y < height - 1
        assert agent_start_pos not in goal_positions, "Agent in goal position"

        if lava_positions is None:
            # generate default lava positions relative to bottom left corner
            # (goal is ignored due to order of tile placement)
            temp_lava_positions = []
            for y in range(1, height - 1):
                temp_lava_positions.append((1, y))
            for y in range(height - 3, height - 8, -1):
                temp_lava_positions.append((3, y))
            temp_lava_positions.extend([(6, height - 5), (6, height - 6)])
        else:
            temp_lava_positions = lava_positions

        assert agent_start_pos not in temp_lava_positions, \
            "Agent in lava position"

        if spiky_active and spiky_positions is None:
            # generate default spiky positions relative to bottom left corner
            # (goal is ignored due to order of tile placement)
            temp_spiky_positions = []
            for y in range(1, height - 2):
                temp_spiky_positions.append((2, y))
        else:
            temp_spiky_positions = spiky_positions
        
        assert reward_spec[SPIKY_TILE_REWARD] == 0 or spiky_active, \
            "Set the spiky tile reward to 0 if spiky tiles are not activated"

        # Define instance variables not yet contained in MiniGridEnv
        # These variables don't need to be reset when resetting the env
        # The default MiniGridEnv.reset() can thus be used
        self.agent_start_pos = np.array(agent_start_pos)
        self.slip_proba = slip_proba
        self.reward_spec = reward_spec
        self.goal_positions = goal_positions
        self.lava_positions = temp_lava_positions
        self.spiky_active = spiky_active
        self.spiky_positions = temp_spiky_positions
        self.new_actions = RiskyPathEnv.Actions
        self.show_agent_dir = show_agent_dir
        self.wall_rebound = wall_rebound

        # Call superclass initialisation
        # As the super __init__() is called, the action_space is set
        # to the default MiniGridEnv action space.
        # A workaround to this is to reset the action space in the gen_grid
        # method
        super().__init__(
            width=width,
            height=height,
            max_steps=max_steps,
            seed=seed
        )

    def _gen_grid(self, width, height):
        """Overrides MiniGridEnv._gen_grid(). Must be implemented in each
        subclass. Order of tile creation matters, which means the last
        set tile on a position will always be placed.
        
        Additional details:
        The environments action_space is set in this method instead of the 
        __init__ method. This is due to the fact that the MiniGridEnv.__init__
        method is called as a last step in RiskyPathEnv.__init__ and the action
        space is set to have 7 distinct actions. As this does not conform to my
        environment specification (only 4 distinct actions), this workaround is
        used."""
        # Workaround for correctly specifying the action_space attribute
        self.action_space = spaces.Discrete(len(RiskyPathEnv.Actions))

        # create an empty grid
        self.grid = Grid(width, height)
        if not self.show_agent_dir:
            Grid.set_show_agent_dir(False)

        # place the surrounding walls
        self.grid.wall_rect(0, 0, width, height)

        # place the lava tiles (relative to bottom left corner)
        for pos in self.lava_positions:
            self.put_obj(Lava(), *pos)

        # place the spiky tiles (relative to bottom left corner)
        if self.spiky_active:
            for pos in self.spiky_positions:
                self.put_obj(SpikyTile(), *pos)

        # place the goal tile(s) last to override any other tile
        for pos in self.goal_positions:
            self.put_obj(Goal(), *pos)

        # place the agent looking up
        self.agent_pos = self.agent_start_pos
        self.agent_dir = 3

        # assign the textual mission string (expected by MiniGrid)
        self.mission = "Get to the green Goal tile"

    def step(self, action):
        """Overrides MiniGridEnv.step()

        Overrides MiniGridEnv.step() as MiniGridEnv logic is not sufficient
        for this environment (Non-directional agent,
        non-sparse reward option). Under the hood, this method first changes
        the orientation of the agent similar to MiniGridEnv, except that the
        time step is not finished directly afterwards. The agent will move
        forward in the new direction if this is possible. The collisions with
        objects is still specified as in the default MiniGridEnv
        implementation.

        Args:
            action: Should be contained in self.action_space

        Returns:
            (observation, reward, done, info)
        """         

        self.step_count += 1
        reward = self.reward_spec[STEP_PENALTY]
        done = False

        previous_position = self.agent_pos

        # Only apply movement logic if agent should be able to move
        if self.can_move:
            # choose new agent direction according to minigrid.DIR_TO_VEC
            if action == self.new_actions.west:
                self.agent_dir = 2
            elif action == self.new_actions.north:
                self.agent_dir = 3
            elif action == self.new_actions.east:
                self.agent_dir = 0
            elif action == self.new_actions.south:
                self.agent_dir = 1
            else:
                assert False, "Unknown action."

            # Get the contents of the cell in front of the agent
            fwd_pos = self.front_pos
            next_cell = self.grid.get(*fwd_pos)

            # check if the agent slips in this step
            # check explicitly that slipping is allowed
            if self.slip_proba > 0:
                rnd_val = self.np_random.random()  
                slip_now = rnd_val < self.slip_proba
            else:
                slip_now = False

            # move one step and get the reward

            if (next_cell == None or next_cell.can_overlap()) and not slip_now:
                self.agent_pos = fwd_pos
            elif self.wall_rebound or slip_now:
                # rebound/slip
                # (currently: rebound on walls, closed doors, key, ball, box)
                # rebound can happen behind agent pos/dir or on the sides
                # slip can happen to either adjacent side
                tmp_rebound_slip = []
                current_pos = np.array(self.agent_pos)
                current_dir = DIR_TO_VEC[self.agent_dir]
                behind_pos = current_pos - current_dir
                tmp_rebound_slip.append(behind_pos)
                # compute positions perpendicular to agent_dir
                # and adjacent to agent_pos
                side_dir = np.flip(current_dir, 0)
                side_pos_1 = current_pos + side_dir
                side_pos_2 = current_pos - side_dir
                tmp_rebound_slip.append(side_pos_1)
                tmp_rebound_slip.append(side_pos_2)
                # append position in front of the agent
                tmp_rebound_slip.append(fwd_pos)

                # get valid options for next cell
                rebound_slip_options = []
                for candidate in tmp_rebound_slip:
                    cell = self.grid.get(*candidate)
                    # make sure the agent can be on the cell
                    if cell is None or cell.can_overlap():
                        rebound_slip_options.append(candidate)
                
                # choose from valid candidates or keep current position if empty
                if len(rebound_slip_options) > 0:
                    index = self.np_random.choice(len(rebound_slip_options))
                    self.agent_pos = rebound_slip_options[index]

        # reassign next cell to make sure to check for collisions & rewards
        next_cell = self.grid.get(*self.agent_pos)
        
        # check for cells and corresponding rewards / episode end
        if next_cell != None and next_cell.type == 'goal':
            if self.reward_spec[ABSORBING_STATES]:
                reward += self.reward_spec[ABSORBING_REWARD_GOAL]
            else:
                done = True
                reward += self.reward_spec[GOAL_REWARD]
        if next_cell != None and next_cell.type == 'lava':
            if self.reward_spec[ABSORBING_STATES]:
                reward += self.reward_spec[ABSORBING_REWARD_LAVA]
            else:
                done = True
                reward += self.reward_spec[LAVA_REWARD]
        if next_cell != None and next_cell.type == 'spiky_floor':
            reward += self.reward_spec[SPIKY_TILE_REWARD]

        # finish the step
        if self.step_count >= self.max_steps:
            done = True

        obs = self.gen_obs()

        info = {
            "agent_pos" : self.agent_pos,
            "previous_pos" : previous_position,
            "actual_movement_vec" : self.agent_pos - previous_position,
            "intended_movement_vec" : DIR_TO_VEC[self.agent_dir],
            "slipped" : slip_now,
            "current_cell_type" : next_cell.type \
                if next_cell is not None else None
        }

        return obs, reward, done, info

    def render(self, mode='human', close=False, highlight=False, tile_size=...):
        """Override render method to not highlight cells by default.
        Highlighted cells might confuse users as they suggest that the agent
        does not have full observability over the environment."""

        return super().render(
            mode=mode,
            close=close,
            highlight=highlight,
            tile_size=tile_size
        )
    
    @property
    def can_move(self):
        """Make sure that the agent can move from its current position.
        This is especially useful when absorbing states are activated."""
        return self.grid.get(*self.agent_pos) is None \
            or not self.grid.get(*self.agent_pos).type in ['goal', 'lava']

    @property
    def tensor_observation_space(self):
        """Returns the observation space of the environment for tensor
        observations and the array shape.
        The space dimensionality is dependent on whether or not spiky
        tiles are used."""
        if self.spiky_active:
            # for each position, 5 dimensions (agent, wall, lava, goal, spiky)
            # normal floor tile is implicit
            shape = (self.grid.width, self.grid.height, 5)
        else:
            # reduce dimension by 1 (no spiky tiles)
            shape = (self.grid.width, self.grid.height, 4)
        return spaces.Box(low=0, high=1, shape=shape, dtype=int), shape

    def tensor_obs(self):
        """Returns a (full) tensor observation of the environment.

        The tensor is computed dependent on the reward specification:
        when there is no specified reward/penalty for spiky tiles, they
        are not considered in the computation of the tensor.

        Returns:
            NDArray: environment's tensor observation
        """
        obs_shape = self.tensor_observation_space[1]
        tensor_obs = np.zeros(obs_shape, dtype=int)
        # 0 is agent position
        # 1 is wall positions
        # 2 is lava positions
        # 3 is goal positions
        # (4 is spiky floor position)
        agent_x, agent_y = self.agent_pos
        tensor_obs[agent_x, agent_y, 0] = 1

        for x in range(self.grid.width):
            for y in range(self.grid.height):
                current_cell = self.grid.get(x, y)
                if current_cell is not None:
                    if current_cell.type == "wall":
                        tensor_obs[x, y, 1] = 1
                    elif current_cell.type == "lava":
                        tensor_obs[x, y, 2] = 1
                    elif current_cell.type == "goal":
                        tensor_obs[x, y, 3] = 1
                    # next block only executes if spiky tiles have been set
                    elif current_cell.type == "spiky_floor":
                        tensor_obs[x, y, 4] = 1
        return tensor_obs

# -------* Registration *-------

# ---- V0 ----
# Default environment specification - tensor observation
register(
    id="MiniGrid-RiskyPath-v0",
    entry_point='gym_minigrid.envs:RiskyPathEnv'
)