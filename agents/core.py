import numpy as np
import random

from numba import jit
from numba import int32, float32

n_actions = 6

eps = 1e-7

__stats = np.zeros((6, n_actions), dtype=np.float32)

@jit(nopython=True, cache=True)
def findZero(arr):
    for i in range(n_actions):
        if arr[i] == 0:
            return i
    return False

@jit(nopython=True,cache=True)
def select_index(index,child,node_stats):

    trace = []

    while True:

        trace.append(index)

        is_leaf_node = True

        _child_nodes = []
        for i in range(n_actions):
            if child[index][i] != 0:
                _child_nodes.append(child[index][i])

        len_c = len(_child_nodes)

        if len_c == 0:
            break

        has_unvisited_node = False

        _stats = np.zeros((2, len_c), dtype=np.float32)

        _max = 1.0

        for i in range(len_c):
            _idx = _child_nodes[i]
            _stats[0][i] = node_stats[_idx][0]
            _stats[1][i] = node_stats[_idx][1]
            _max = max(_max,node_stats[_idx][4])
            if node_stats[_idx][0] == 0:
                index = _idx
                has_unvisited_node = True
                break

        if has_unvisited_node:
            continue

        _t = np.sum(_stats[0]) 

        _c = _max * np.sqrt( np.log(_t) / _stats[0] )

        _q = _stats[1] / _stats[0]

        _v = _q + _c 
        
        _a = np.argmax(_v)

        index = _child_nodes[_a]

    return trace

@jit(nopython=True,cache=True)
def backup_trace(trace,node_stats,value):

    for idx in trace:
        v = value - node_stats[idx][2] 
        node_stats[idx][0] += 1
        node_stats[idx][1] += v
        node_stats[idx][3] += v * v
        node_stats[idx][4] = max(v,node_stats[idx][4])

@jit(nopython=True,cache=True)
def get_all_childs(index,child):
    
    to_traverse = [index,]

    traversed = []

    i = 0
    while i < len(to_traverse):
        idx = to_traverse[i]
        if idx not in traversed:
            to_traverse += list(child[idx])   
            traversed.append(idx)
        i += 1
    return set(to_traverse)

@jit(nopython=True,cache=True)
def choose_action(p):
    _cdf = p.cumsum()

    rnd = np.random.rand()

    _a = np.searchsorted(_cdf,rnd)

    return _a

@jit(nopython=True,cache=True)
def atomicSelect(stats):

    _n_sum = np.sum(stats[0])
    
    _max = max(1, np.amax(stats[5]))

    _q = stats[3]

    _c = _max * np.sqrt( np.log(_n_sum) / stats[0] )

    return np.argmax( _q + _c )

def update_child_info(trace, action, child_info):
    for i in range(len(action)):
        s = trace[i]
        _s = trace[i+1]
        a = action[i]
        found = False
        for pair in child_info[s][a]:
            if pair[0] == _s:
                found = True
                pair[1] += 1
                break
        if not found:
            child_info[s][a] = np.concatenate((child_info[s][a], [[_s, 1]]))

@jit(nopython=True,cache=True)
def atomicFill(act, stats, node_stats, childs):

    val = 0
    counts = 0
    val_2 =0
    m = 0

    for j in range(len(childs)):
        n = childs[j][0]
        c = childs[j][1]
        _v = node_stats[n][1] / node_stats[n][0]
        val += c * _v
        counts += c   
        val_2 += node_stats[n][3]
        m = max(m, node_stats[n][4])

    stats[0][act] = counts
    stats[1][act] = 0
    stats[2][act] = 0
    stats[3][act] = val / counts
    stats[4][act] = val_2
    stats[5][act] = m


def fill_child_stats(idx, node_stats, child_info):

    global __stats
    __stats.fill(0)

    for i in range(n_actions):
        if len(child_info[idx][i]) > 0:
            atomicFill(i, __stats, node_stats, child_info[idx][i])
       
    return __stats 

def get_all_child_2(index, child_info):
    to_traverse = [index, ]
    traversed = set([0])

    i = 0
    while i < len(to_traverse):
        idx = to_traverse[i]
        if idx not in traversed:
            traversed.add(idx)
            _list = [p[0] for a in range(n_actions) for p in child_info[idx][a]]
            to_traverse += _list
        i += 1

    return traversed

def findZero_2(index, child_info):
    for i in range(n_actions):
        if len(child_info[index][i]) == 0:
            return i
    return False

@jit(nopython=True,cache=True)
def _tmp_func(stats, act, node_stats, childs):
    q_max = 0
    for i in range(len(childs)):
        idx = childs[i][0]
        node = node_stats[idx]
        stats[0][act] += childs[i][1]
        stats[1][act] += childs[i][1] * node[1] / node[0]
        stats[2][act] += childs[i][1] * node[4] * np.sqrt( 1 / node[0] )
        q_max = max(q_max, node[4])
    stats[1][act] /= (stats[0][act]+eps)
    stats[2][act] /= (stats[0][act]+eps)
    stats[3][act] = len(childs)

    return q_max 

@jit(nopython=True,cache=True)
def _tmp_select(stats, v_max):
    v_max = v_max + eps
    _p = ( stats[3] + 0.5 ) / ( stats[0] + 1 )
    _n = np.sqrt(np.log(np.sum(stats[0])))
    _u = _n * ( _p * v_max * np.sqrt( 1 / stats[0] ) + ( 1 - _p ) * stats[2] )
    return np.argmax( stats[1] + _u )

def select_index_2(game, node_dict, node_stats, child_info):

    trace = []
    action = []
    idx = node_dict.get(game)

    while idx and not game.end:

        trace.append(idx)

        _a = findZero_2(idx, child_info)

        if _a is False:

            _stats_tmp = np.zeros((4, n_actions), dtype=np.float32)

            _max = max([_tmp_func(_stats_tmp, i, node_stats, child_info[idx][i]) for i in range(n_actions)])
            _a = _tmp_select(_stats_tmp, _max)          
        action.append(_a)

        game.play(_a)

        idx = node_dict.get(game)

    return trace, action

@jit(nopython=True,cache=True)
def select_index_3(index,child,node_stats):

    trace = []

    while True:

        trace.append(index)

        _child_nodes = []
        for i in range(n_actions):
            if child[index][i] != 0:
                _child_nodes.append(child[index][i])

        len_c = len(_child_nodes)

        if len_c == 0:
            break

        has_unvisited_node = False

        _stats = np.zeros((2, len_c), dtype=np.float32)

        for i in range(len_c):
            _idx = _child_nodes[i]
            if node_stats[_idx][0] == 0:
                index = _idx
                has_unvisited_node = True
                break
            _stats[0][i] = node_stats[_idx][1]
            _stats[1][i] = np.sqrt(node_stats[_idx][3] / node_stats[_idx][0])

        if has_unvisited_node:
            continue


        _c = _stats[1]

        _q = _stats[0]

        _v = _q + _c 
        
        _a = np.argmax(_v)

        index = _child_nodes[_a]

    return trace

@jit(nopython=True,cache=True)
def backup_trace_3(trace,node_stats,value):
    alpha = 0.01
    for idx in trace:
        v = value - node_stats[idx][2] 
        if node_stats[idx][0] == 0:
            node_stats[idx][1] = v 
        else:
            _v = v - node_stats[idx][1]
            node_stats[idx][1] += alpha * _v
            node_stats[idx][3] = (1-alpha) * (node_stats[idx][3] + alpha * _v * _v)
        node_stats[idx][0] += 1
        node_stats[idx][4] = max(v,node_stats[idx][4])

