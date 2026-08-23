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


def load_initial_placement(params, placedb, init_pl_file):
    """
    @brief Load initial placement from a .pl file.
    @return dictionary mapping node names to (x, y, z) positions
    
    File format: node_name x y z [FIXED]
    """
    if not os.path.exists(init_pl_file):
        logging.error("Initial placement file not found: %s" % init_pl_file)
        return None
    
    logging.info("Loading initial placement from: %s" % init_pl_file)
    
    init_pos = {}
    with open(init_pl_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) >= 3:
                node_name = parts[0]
                try:
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3]) if len(parts) >= 4 else 0
                    # Skip FIXED nodes - they are already handled by placedb
                    if len(parts) >= 5 and parts[4].upper() == 'FIXED':
                        continue
                    init_pos[node_name] = (x, y, z)
                except ValueError:
                    continue
    
    logging.info("Loaded %d movable node positions" % len(init_pos))
    return init_pos


def apply_initial_placement(placedb, init_pos):
    """
    @brief Apply initial placement positions to placedb.
    
    IMPORTANT: The placement file coordinates are PHYSICAL coordinates,
    same as placedb coordinates. No scaling is needed!
    
    The coordinate system in DREAMPlaceFPGA:
    - Site coordinates = Physical coordinates (1:1 mapping)
    - design.scl SITEMAP dimensions = placedb boundaries
    """
    if not init_pos:
        return 0
    
    # Build name to index mapping for movable nodes
    node_name_to_idx = {}
    for i in range(placedb.num_movable_nodes):
        node_name_to_idx[placedb.node_names[i]] = i
    
    # Get placedb boundaries for validation
    xl = getattr(placedb, 'xl', 0)
    yl = getattr(placedb, 'yl', 0)
    xh = getattr(placedb, 'xh', float('inf'))
    yh = getattr(placedb, 'yh', float('inf'))
    
    logging.info("PlaceDB boundaries: x=[%.2f, %.2f], y=[%.2f, %.2f]" % (xl, xh, yl, yh))
    
    # Analyze init coordinates
    movable_coords = [(name, coords) for name, coords in init_pos.items() 
                      if name in node_name_to_idx]
    
    if not movable_coords:
        logging.error("No matching movable nodes found in init file!")
        return 0
    
    x_vals = [c[1][0] for c in movable_coords]
    y_vals = [c[1][1] for c in movable_coords]
    logging.info("Init file coordinate range: x=[%.2f, %.2f], y=[%.2f, %.2f]" 
                % (min(x_vals), max(x_vals), min(y_vals), max(y_vals)))
    
    # Check if coordinates are within placedb boundaries
    coords_valid = (min(x_vals) >= xl and max(x_vals) <= xh and
                    min(y_vals) >= yl and max(y_vals) <= yh)
    
    if coords_valid:
        logging.info("Coordinates are within valid range - using directly (no scaling)")
    else:
        logging.warning("Coordinates exceed boundaries - will clamp to valid range")
    
    # Apply positions directly (coordinates are already in physical units)
    updated = 0
    clamped = 0
    for node_name, (x, y, z) in init_pos.items():
        if node_name not in node_name_to_idx:
            continue
        
        idx = node_name_to_idx[node_name]
        
        # Validate and clamp if necessary
        x_final = x
        y_final = y
        
        if x < xl or x > xh or y < yl or y > yh:
            x_final = max(xl, min(xh, x))
            y_final = max(yl, min(yh, y))
            clamped += 1
        
        # Check for invalid values
        if np.isnan(x_final) or np.isnan(y_final) or np.isinf(x_final) or np.isinf(y_final):
            logging.warning("Invalid coordinate for %s: (%.2f, %.2f), skipping" % (node_name, x, y))
            continue
        
        placedb.node_x[idx] = x_final
        placedb.node_y[idx] = y_final
        if hasattr(placedb, 'node_z') and placedb.node_z is not None:
            placedb.node_z[idx] = z
        updated += 1
    
    logging.info("Applied initial placement: %d nodes updated, %d clamped" % (updated, clamped))
    
    # Show sample positions
    logging.info("Sample positions after apply:")
    for i in range(min(3, placedb.num_movable_nodes)):
        name = placedb.node_names[i]
        if name in init_pos:
            logging.info("  %s: (%.4f, %.4f)" % (name, placedb.node_x[i], placedb.node_y[i]))
    
    return updated


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
    
    # Read Database
    placedb = PlaceDBFPGA()
    placedb(params)

    # Load and apply initial placement if specified
   
    use_init_placement = False
    if hasattr(params, 'init_placement_file') and params.init_placement_file:
        init_pos = load_initial_placement(params, placedb, params.init_placement_file)
        
        if init_pos:
            updated = apply_initial_placement(placedb, init_pos)
            if updated > 0:
                use_init_placement = True
                logging.info("Using initial placement: %d nodes initialized" % updated)
    if use_init_placement:
        x = np.array(placedb.node_x[:placedb.num_movable_nodes])
        y = np.array(placedb.node_y[:placedb.num_movable_nodes])
        logging.info("After init placement: x in [%.1f, %.1f], y in [%.1f, %.1f]" %
                    (x.min(), x.max(), y.min(), y.max()))
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            logging.error("NaN/Inf in placedb node positions right after init!")

    if params.write_io_placement_flag:
        placedb.writeIOPlacement(params, 'place_io_cells.tcl')

    # Initialize timer
    timer = None
    if params.timing_driven_flag:
        timer = Timer(params, placedb)

    # CRITICAL: Disable random init when using initial placement
    original_random_init = params.random_center_init_flag
    #初始布局时注释掉
    if use_init_placement:
       params.random_center_init_flag = 0
       logging.info("Disabled random_center_init_flag to preserve initial placement")
    
    # Initialize Placer
    placer = NonLinearPlaceFPGA(params, placedb, timer)
    
    # Update placer's position tensor with initial placement
    #初始布局时注释掉
    #if use_init_placement:
     #   update_placer_pos(placer, placedb)
    
    # Restore flag
    params.random_center_init_flag = original_random_init
    
    # Run placement
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
