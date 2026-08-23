##
# @file   Placer.py
# @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
# @date   Sep 2020
# @brief  Main file to run the entire placement flow. 
# @modified FINAL VERSION - Correct initial placement handling
#

import matplotlib 
matplotlib.use('Agg')
import os
import sys 
import time 
import numpy as np 
import logging
import json
# for consistency between python2 and python3
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
	sys.path.append(root_dir)
import dreamplacefpga.configure as configure 
from Params import *
from PlaceDB import *
from NonLinearPlace import *
from IFWriter import * 
from Timer import *
import pdb 

def apply_custom_node_sizes_from_json(placedb, size_file):
    """Override placedb.node_size_x/y using a JSON file.

    Supported JSON formats:
      1) {"nodes": {"nodeA": {"w": 3.0, "h": 2.0}, "nodeB": 9.0, ...}}
      2) {"nodeA": [3.0, 2.0], "nodeB": {"area": 9.0}, ...}
      3) {"nodeA": 9.0, ...}  # scalar treated as area (square)
    Units: site grid units (consistent with .scl / PlaceDB site coordinates).
    """
    if size_file is None:
        return
    size_file = str(size_file).strip()
    if not size_file:
        return
    if not os.path.isfile(size_file):
        logging.warning("cluster_node_size_file not found: %s", size_file)
        return

    with open(size_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # unwrap {"nodes": {...}}
    if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], dict):
        data = data["nodes"]

    if not isinstance(data, dict):
        logging.warning("cluster_node_size_file must be a dict; got %s", type(data))
        return

    updated = 0
    skipped = 0

    for name, val in data.items():
        if name not in placedb.node_name2id_map:
            skipped += 1
            continue

        w = h = None

        if isinstance(val, dict):
            # explicit sizes
            w = val.get("w", val.get("width", val.get("size_x")))
            h = val.get("h", val.get("height", val.get("size_y")))
            # or area -> square
            if (w is None or h is None) and ("area" in val):
                try:
                    side = float(val["area"]) ** 0.5
                    w = w if w is not None else side
                    h = h if h is not None else side
                except Exception:
                    w = h = None
        elif isinstance(val, (list, tuple)) and len(val) >= 2:
            w, h = val[0], val[1]
        else:
            # scalar treated as area
            try:
                side = float(val) ** 0.5
                w = h = side
            except Exception:
                w = h = None

        if w is None or h is None:
            skipped += 1
            continue

        node_id = placedb.node_name2id_map[name]
        placedb.node_size_x[node_id] = float(w)
        placedb.node_size_y[node_id] = float(h)
        updated += 1
    
    logging.info("Applied custom node sizes: updated=%d skipped=%d file=%s", updated, skipped, size_file)
    



def update_placer_pos(placer, placedb):
    """
    @brief Update placer's position tensor from placedb coordinates.
    
    Position tensor format in DREAMPlaceFPGA:
    - Length: 2 * num_nodes
    - x coordinates: [0, num_nodes)
    - y coordinates: [num_nodes, 2*num_nodes)
    - Only first num_movable_nodes in each section are movable
    """
    import torch
    
    if not hasattr(placer, 'pos') or placer.pos is None:
        logging.warning("Placer has no 'pos' attribute")
        return
    
    # Get position tensor(s)
    if isinstance(placer.pos, torch.nn.ParameterList):
        pos_list = list(placer.pos)
    elif isinstance(placer.pos, list):
        pos_list = placer.pos
    else:
        pos_list = [placer.pos]
    
    num_movable = placedb.num_movable_nodes
    num_nodes = placedb.num_nodes
    
    logging.info("Updating placer position tensor...")
    logging.info("  num_movable_nodes = %d, num_nodes = %d" % (num_movable, num_nodes))
    
    for pos_idx, pos in enumerate(pos_list):
        if isinstance(pos, torch.nn.Parameter):
            pos_tensor = pos.data
        else:
            pos_tensor = pos
        
        tensor_len = len(pos_tensor)
        logging.info("  pos[%d]: length=%d" % (pos_idx, tensor_len))
        
        # Determine format based on tensor length
        if tensor_len == 2 * num_nodes:
            # Standard format: [x_all_nodes..., y_all_nodes...]
            x_offset = 0
            y_offset = num_nodes
        elif tensor_len == 2 * num_movable:
            # Movable-only format: [x_movable..., y_movable...]
            x_offset = 0
            y_offset = num_movable
        else:
            logging.warning("  Unexpected tensor length, attempting to use half-split format")
            x_offset = 0
            y_offset = tensor_len // 2
        
        # Update positions
        updated = 0
        for idx in range(num_movable):
            x_idx = x_offset + idx
            y_idx = y_offset + idx
            
            if x_idx >= tensor_len or y_idx >= tensor_len:
                logging.error("Index out of bounds at idx=%d" % idx)
                break
            
            x_val = float(placedb.node_x[idx])
            y_val = float(placedb.node_y[idx])
            
            if np.isnan(x_val) or np.isnan(y_val) or np.isinf(x_val) or np.isinf(y_val):
                continue
            
            pos_tensor[x_idx] = x_val
            pos_tensor[y_idx] = y_val
            updated += 1
        
        logging.info("  Updated %d/%d movable nodes in pos[%d]" % (updated, num_movable, pos_idx))


def placeFPGA(params):
    """
    @brief Top API to run the entire placement flow. 
    """
    assert (not params.gpu) or configure.compile_configurations["CUDA_FOUND"] == 'TRUE', \
            "CANNOT enable GPU without CUDA compiled"

    np.random.seed(params.random_seed)
    start = time.time()
    # --- DEBUG: 进入 placeFPGA 时打印标志位 ---
    logging.info(">>> [DEBUG] enter placeFPGA: "
                 "global_place_flag=%r (type=%s), legalize_flag=%r (type=%s), detailed_place_flag=%r (type=%s)" %
                 (params.global_place_flag, type(params.global_place_flag),
                  params.legalize_flag, type(params.legalize_flag),
                  params.detailed_place_flag, type(params.detailed_place_flag)))
    
    placedb = PlaceDBFPGA()
    placedb.read(params) #Call function

    # Optional: override node sizes (e.g., cluster-level placement)
    # 2) 在 initialize 之前应用 cluster 尺寸
    if getattr(params, "cluster_node_size_file", ""):
        apply_custom_node_sizes_from_json(placedb, params.cluster_node_size_file)

    # 3) 用更新后的 node_size_x/y 做初始化与面积统计
    placedb.initialize(params)
    #logging.info("Reading database takes %.2f seconds" % (time.time()-start))

    # write out xdc file
    # placedb.writeXDC(params, "design_constr.xdc")

    # Random Initial Placement 
    placer = NonLinearPlaceFPGA(params, placedb)
    #logging.info("non-linear placement initialization takes %.2f seconds" % (time.time()-tt))
    metrics = placer(params, placedb)
    logging.info("Placement completed in %.2f seconds" % (time.time()-start))

    # Write output
    path = "%s/%s" % (params.result_dir, params.design_name())
    if not os.path.exists(path):
        os.system("mkdir -p %s" % (path))
        
    if params.global_place_flag and params.legalize_flag == 0:
        gp_out_file = os.path.join(path, "%s.gp.pl" % (params.design_name()))
        placedb.write(params, gp_out_file)
        
        if os.path.exists("thirdparty/elfPlace_LG_DP"):
            cp_cmd = "cp %s gp.pl" %(gp_out_file)
            os.system(cp_cmd)
            out_file = os.path.join(path, "%s_final.%s" % (params.design_name(), params.solution_file_suffix()))
            cmd = "./thirdparty/elfPlace_LG_DP --aux %s --numThreads %s --pl %s" % (params.aux_input, params.num_threads, out_file)
            logging.info("Legalization: %s" % (cmd))
            tt = time.time()
            os.system(cmd)
            logging.info("Legalization completed in %.3f seconds" % (time.time()-tt))
        else:
            logging.warning("elfPlace_LG_DP not found")

    elif params.legalize_flag:
        final_out_file = os.path.join(path, "%s.final.%s" % (params.design_name(), params.solution_file_suffix()))
        placedb.writeFinalSolution(params, final_out_file)
        logging.info("Detailed Placement not run")

    if params.write_tcl_flag:
        placedb.writeTcl(params, 'place_cells.tcl')

    logging.info("Completed Placement in %.3f seconds" % (time.time()-start))

    if params.enable_if == 1:
        tt = time.time()
        logging.info("Start writing solution to Interchange Format(IF)")
        schema_dir = os.path.join(os.path.dirname(__file__), '../thirdparty/fpga-interchange-schema/interchange')
        db2phys = db_to_physicalnetlist(placedb, schema_dir, params.interchange_device)
        phys_netlist = db2phys.build_physicalnetlist(placedb, params)
        if_writer = IFWriter(schema_dir)
        physical_netlist = if_writer.build_IF(phys_netlist)
        if_file = os.path.join(path, "%s.phys" % (params.design_name()))
        if_writer.write_IF(physical_netlist, if_file)
        logging.info("Interchange Format(IF) Writer completed in %.3f seconds" % (time.time()-tt))


if __name__ == "__main__":
    logging.root.name = 'DREAMPlaceFPGA'
    logging.basicConfig(level=logging.INFO, format='[%(levelname)-7s] %(name)s - %(message)s', stream=sys.stdout)

    if len(sys.argv) < 2:
        logging.error("Input parameters required in json format")
        sys.exit(1)
        
    paramsArray = []
    for i in range(1, len(sys.argv)):
        params = ParamsFPGA()
        params.load(sys.argv[i])
        paramsArray.append(params)
    logging.info("Parameters[%d] = %s" % (len(paramsArray), paramsArray))

    import torch
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.enabled = False 
    torch.manual_seed(params.random_seed)
    np.random.seed(params.random_seed)
    if params.gpu:
        torch.cuda.manual_seed_all(params.random_seed)
        torch.cuda.manual_seed(params.random_seed)

    for params in paramsArray: 
        placeFPGA(params)
