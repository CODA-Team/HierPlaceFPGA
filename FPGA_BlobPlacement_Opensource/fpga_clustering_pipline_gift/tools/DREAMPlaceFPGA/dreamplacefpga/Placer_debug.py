##
# @file   Placer.py
# @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
# @date   Sep 2020
# @brief  Main file to run the entire placement flow. 
# @modified DEBUG VERSION - Added extensive logging for initial placement diagnosis
#

import matplotlib 
matplotlib.use('Agg')
import os
import sys 
import time 
import numpy as np 
import logging
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


def load_initial_placement(params, placedb, init_pl_file):
    """
    @brief Load initial placement from a .pl file.
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
                    # Skip FIXED nodes
                    if len(parts) >= 5 and parts[4] == 'FIXED':
                        continue
                    init_pos[node_name] = (x, y, z)
                except ValueError:
                    continue
    
    logging.info("Loaded %d movable node positions" % len(init_pos))
    return init_pos


def diagnose_coordinate_system(placedb, init_pos):
    """
    @brief Diagnose coordinate system mismatch between init file and placedb
    """
    logging.info("=" * 60)
    logging.info("COORDINATE SYSTEM DIAGNOSIS")
    logging.info("=" * 60)
    
    # PlaceDB info
    xl = getattr(placedb, 'xl', 0)
    yl = getattr(placedb, 'yl', 0)
    xh = getattr(placedb, 'xh', 1)
    yh = getattr(placedb, 'yh', 1)
    
    logging.info("PlaceDB boundaries:")
    logging.info("  xl=%.6f, xh=%.6f (width=%.6f)" % (xl, xh, xh-xl))
    logging.info("  yl=%.6f, yh=%.6f (height=%.6f)" % (yl, yh, yh-yl))
    
    # Current placedb node positions (first few movable nodes)
    logging.info("\nCurrent placedb positions (first 5 movable nodes):")
    for i in range(min(5, placedb.num_movable_nodes)):
        name = placedb.node_names[i]
        x = placedb.node_x[i]
        y = placedb.node_y[i]
        logging.info("  %s: (%.6f, %.6f)" % (name, x, y))
    
    # Init file positions
    if init_pos:
        sample = list(init_pos.items())[:5]
        logging.info("\nInit file positions (first 5):")
        for name, (x, y, z) in sample:
            logging.info("  %s: (%.6f, %.6f, %.6f)" % (name, x, y, z))
        
        # Compute ranges
        all_coords = list(init_pos.values())
        init_x_min = min(c[0] for c in all_coords)
        init_x_max = max(c[0] for c in all_coords)
        init_y_min = min(c[1] for c in all_coords)
        init_y_max = max(c[1] for c in all_coords)
        
        logging.info("\nInit file coordinate ranges:")
        logging.info("  x: [%.6f, %.6f]" % (init_x_min, init_x_max))
        logging.info("  y: [%.6f, %.6f]" % (init_y_min, init_y_max))
        
        # Diagnose mismatch
        logging.info("\n*** DIAGNOSIS ***")
        
        placedb_range_x = xh - xl
        placedb_range_y = yh - yl
        init_range_x = init_x_max - init_x_min
        init_range_y = init_y_max - init_y_min
        
        if init_x_max > xh or init_y_max > yh:
            logging.warning("Init coords EXCEED placedb boundaries!")
            logging.warning("This suggests init file uses SITE INDICES, not physical coords")
            
            # Compute required scaling
            scale_x = placedb_range_x / (init_range_x + 1) if init_range_x > 0 else 1.0
            scale_y = placedb_range_y / (init_range_y + 1) if init_range_y > 0 else 1.0
            logging.info("Suggested scale factors: x=%.6f, y=%.6f" % (scale_x, scale_y))
            
        elif placedb_range_x > 10 and init_x_max <= 1.0:
            logging.warning("Init coords appear NORMALIZED (0-1)")
            logging.warning("PlaceDB uses larger physical coordinates")
            
        else:
            logging.info("Coordinate systems appear compatible")
    
    logging.info("=" * 60)


def apply_initial_placement_v2(placedb, init_pos):
    """
    @brief Apply initial placement with CORRECT coordinate transformation.
           
    DREAMPlaceFPGA coordinate system:
    - Physical coordinates within [xl, xh] x [yl, yh]
    - These are typically normalized or scaled site coordinates
    
    Init file format:
    - Site indices (integer-like coordinates)
    - Need to transform: physical_coord = site_index * site_width + offset
    """
    if not init_pos:
        return 0
    
    # Build name to index mapping for movable nodes
    node_name_to_idx = {}
    for i in range(placedb.num_movable_nodes):
        node_name_to_idx[placedb.node_names[i]] = i
    
    # Get placedb boundaries
    xl = getattr(placedb, 'xl', 0)
    yl = getattr(placedb, 'yl', 0)
    xh = getattr(placedb, 'xh', 1)
    yh = getattr(placedb, 'yh', 1)
    
    # Analyze init coordinates for movable nodes only
    movable_coords = [(name, coords) for name, coords in init_pos.items() 
                      if name in node_name_to_idx]
    
    if not movable_coords:
        logging.error("No matching movable nodes found!")
        return 0
    
    init_x_min = min(c[1][0] for c in movable_coords)
    init_x_max = max(c[1][0] for c in movable_coords)
    init_y_min = min(c[1][1] for c in movable_coords)
    init_y_max = max(c[1][1] for c in movable_coords)
    
    logging.info("Init coordinate range (movable): x=[%.2f,%.2f], y=[%.2f,%.2f]" 
                % (init_x_min, init_x_max, init_y_min, init_y_max))
    
    # Determine transformation
    # The init file contains site indices, we need to map to physical coordinates
    
    placedb_width = xh - xl
    placedb_height = yh - yl
    
    # Compute scale and offset to map init coords to placedb coords
    # Formula: physical = (site - site_min) / (site_max - site_min + 1) * placedb_range + placedb_min
    
    site_range_x = init_x_max - init_x_min + 1  # +1 because site indices are inclusive
    site_range_y = init_y_max - init_y_min + 1
    
    scale_x = placedb_width / site_range_x if site_range_x > 0 else 1.0
    scale_y = placedb_height / site_range_y if site_range_y > 0 else 1.0
    
    logging.info("Transformation: scale=(%.6f, %.6f)" % (scale_x, scale_y))
    logging.info("  site_to_physical: x' = (x - %.2f) * %.6f + %.6f" 
                % (init_x_min, scale_x, xl))
    logging.info("  site_to_physical: y' = (y - %.2f) * %.6f + %.6f" 
                % (init_y_min, scale_y, yl))
    
    # Apply transformation
    updated = 0
    for node_name, (x, y, z) in init_pos.items():
        if node_name not in node_name_to_idx:
            continue
        
        idx = node_name_to_idx[node_name]
        
        # Transform from site coordinates to physical coordinates
        x_phys = (x - init_x_min) * scale_x + xl
        y_phys = (y - init_y_min) * scale_y + yl
        
        # Add small margin to avoid boundary issues
        margin = 1e-6
        x_phys = max(xl + margin, min(xh - margin, x_phys))
        y_phys = max(yl + margin, min(yh - margin, y_phys))
        
        # Validate
        if np.isnan(x_phys) or np.isnan(y_phys) or np.isinf(x_phys) or np.isinf(y_phys):
            logging.warning("Invalid coord for %s, skipping" % node_name)
            continue
        
        placedb.node_x[idx] = x_phys
        placedb.node_y[idx] = y_phys
        if hasattr(placedb, 'node_z') and placedb.node_z is not None:
            placedb.node_z[idx] = z
        updated += 1
    
    # Show sample results
    logging.info("Sample transformed positions:")
    for i in range(min(3, placedb.num_movable_nodes)):
        name = placedb.node_names[i]
        if name in init_pos:
            orig = init_pos[name]
            logging.info("  %s: site(%.2f,%.2f) -> phys(%.6f,%.6f)" 
                        % (name, orig[0], orig[1], placedb.node_x[i], placedb.node_y[i]))
    
    logging.info("Updated %d movable nodes" % updated)
    return updated


def update_placer_pos_v2(placer, placedb):
    """
    @brief Update placer's position tensor from placedb.
    
    CRITICAL: Must understand the EXACT tensor format used by NonLinearPlaceFPGA.
    This version adds extensive debugging to determine the correct format.
    """
    import torch
    
    if not hasattr(placer, 'pos') or placer.pos is None:
        logging.error("Placer has no 'pos' attribute!")
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
    
    logging.info("=" * 60)
    logging.info("POSITION TENSOR UPDATE")
    logging.info("=" * 60)
    logging.info("num_movable_nodes = %d" % num_movable)
    logging.info("num_nodes = %d" % num_nodes)
    logging.info("Number of pos tensors: %d" % len(pos_list))
    
    for pos_idx, pos in enumerate(pos_list):
        if isinstance(pos, torch.nn.Parameter):
            pos_tensor = pos.data
        else:
            pos_tensor = pos
        
        tensor_len = len(pos_tensor)
        logging.info("\npos[%d]: length=%d, dtype=%s, device=%s" 
                    % (pos_idx, tensor_len, pos_tensor.dtype, pos_tensor.device))
        
        # Determine format
        if tensor_len == 2 * num_movable:
            format_type = "MOVABLE_ONLY"
            x_offset = 0
            y_offset = num_movable
            num_to_update = num_movable
        elif tensor_len == 2 * num_nodes:
            format_type = "ALL_NODES"
            x_offset = 0
            y_offset = num_nodes
            num_to_update = num_movable
        else:
            format_type = "UNKNOWN"
            # Try to infer
            x_offset = 0
            y_offset = tensor_len // 2
            num_to_update = min(num_movable, tensor_len // 2)
            logging.warning("Unknown tensor format! Attempting to infer...")
        
        logging.info("Detected format: %s" % format_type)
        logging.info("x_offset=%d, y_offset=%d, num_to_update=%d" 
                    % (x_offset, y_offset, num_to_update))
        
        # Show current values before update
        if tensor_len >= 2:
            logging.info("BEFORE update:")
            logging.info("  pos[0] (x[0]) = %.6f" % float(pos_tensor[0]))
            logging.info("  pos[%d] (y[0]) = %.6f" % (y_offset, float(pos_tensor[y_offset])))
            if num_to_update > 1:
                logging.info("  pos[1] (x[1]) = %.6f" % float(pos_tensor[1]))
                logging.info("  pos[%d] (y[1]) = %.6f" % (y_offset+1, float(pos_tensor[y_offset+1])))
        
        # Show target values from placedb
        logging.info("Target values from placedb:")
        logging.info("  node_x[0] = %.6f" % float(placedb.node_x[0]))
        logging.info("  node_y[0] = %.6f" % float(placedb.node_y[0]))
        
        # Perform update
        updated = 0
        for idx in range(num_to_update):
            x_idx = x_offset + idx
            y_idx = y_offset + idx
            
            if x_idx >= tensor_len or y_idx >= tensor_len:
                logging.error("Index out of bounds at idx=%d!" % idx)
                break
            
            x_val = float(placedb.node_x[idx])
            y_val = float(placedb.node_y[idx])
            
            if np.isnan(x_val) or np.isnan(y_val) or np.isinf(x_val) or np.isinf(y_val):
                logging.warning("Invalid value at idx=%d: (%.6f, %.6f)" % (idx, x_val, y_val))
                continue
            
            pos_tensor[x_idx] = x_val
            pos_tensor[y_idx] = y_val
            updated += 1
        
        logging.info("Updated %d/%d positions" % (updated, num_to_update))
        
        # Verify update
        if tensor_len >= 2:
            logging.info("AFTER update:")
            logging.info("  pos[0] (x[0]) = %.6f" % float(pos_tensor[0]))
            logging.info("  pos[%d] (y[0]) = %.6f" % (y_offset, float(pos_tensor[y_offset])))
    
    logging.info("=" * 60)


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

    # Load initial placement if specified
    init_pos = None
    use_init_placement = False
    
    if hasattr(params, 'init_placement_file') and params.init_placement_file:
        init_pos = load_initial_placement(params, placedb, params.init_placement_file)
        
        if init_pos:
            # Run diagnosis
            diagnose_coordinate_system(placedb, init_pos)
            
            # Apply with correct transformation
            updated = apply_initial_placement_v2(placedb, init_pos)
            
            if updated > 0:
                use_init_placement = True
                logging.info("Successfully applied initial placement to %d nodes" % updated)
            else:
                logging.warning("Failed to apply initial placement!")

    if params.write_io_placement_flag:
        placedb.writeIOPlacement(params, 'place_io_cells.tcl')

    # Initialize timer
    timer = None
    if params.timing_driven_flag:
        timer = Timer(params, placedb)

    # Initialize Placer
    # CRITICAL: Disable random init if using initial placement
    original_random_init = params.random_center_init_flag
    if use_init_placement:
        params.random_center_init_flag = 0
        logging.info("Set random_center_init_flag = 0 to use initial placement")
    
    placer = NonLinearPlaceFPGA(params, placedb, timer)
    
    # Update placer's position tensor
    if use_init_placement:
        update_placer_pos_v2(placer, placedb)
    
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
            logging.info("Running legalization: %s" % (cmd))
            tt = time.time()
            os.system(cmd)
            logging.info("Legalization completed in %.3f seconds" % (time.time()-tt))
        else:
            logging.warning("elfPlace_LG_DP not found")

    elif params.legalize_flag:
        final_out_file = os.path.join(path, "%s.final.%s" % (params.design_name(), params.solution_file_suffix()))
        placedb.writeFinalSolution(params, final_out_file)

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
    logging.basicConfig(level=logging.DEBUG, format='[%(levelname)-7s] %(name)s - %(message)s', stream=sys.stdout)

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
