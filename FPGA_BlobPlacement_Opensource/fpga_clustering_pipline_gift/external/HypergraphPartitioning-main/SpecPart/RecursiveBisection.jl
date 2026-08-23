#!/usr/bin/env julia
"""
SpecPartRecursiveWrapper_inplace.jl - 在固定目录运行的递归包装器

说明：
- 在 SpecPart 目录下运行，避免相对路径问题
- 保留原始 SpecPart 的所有功能
- 实现递归二分逻辑
"""

using ArgParse
using JSON
using LinearAlgebra
using SparseArrays
using Statistics
using Dates

# ============================================================================
# 设置工作目录为 SpecPart 目录
# ============================================================================

# 切换到 SpecPart 目录（避免相对路径问题）
PROJECT_ROOT = dirname(@__DIR__)
SPECPART_DIR = @__DIR__
cd(PROJECT_ROOT)

# Include original module through an absolute path so the package can move.
include(joinpath(SPECPART_DIR, "SpectralRefinement.jl"))
using .SpectralRefinement

# ============================================================================
# 辅助函数：读写超图文件
# ============================================================================

struct HypergraphData
    num_vertices::Int
    num_hyperedges::Int
    hedges::Vector{Int}  # 超边列表（flat）
    eptr::Vector{Int}    # 超边指针
    vertex_weights::Vector{Float64}
    hyperedge_weights::Vector{Float64}
end

function read_hypergraph_hmetis(filepath::String)
    """读取 hMETIS 格式的超图文件"""
    if !isfile(filepath)
        error("File not found: $filepath")
    end
    
    filesize_bytes = filesize(filepath)
    if filesize_bytes == 0
        error("File is empty: $filepath")
    end
    
    lines = readlines(filepath)
    if isempty(lines)
        error("No lines in file: $filepath (filesize: $filesize_bytes bytes)")
    end
    
    # 过滤空行
    lines = filter(line -> !isempty(strip(line)), lines)
    if isempty(lines)
        error("No non-empty lines in file: $filepath")
    end
    
    header = split(strip(lines[1]))
    if length(header) < 2
        error("Invalid header format in $filepath. Header line: $(lines[1])")
    end
    
    num_hyperedges = parse(Int, header[1])
    num_vertices = parse(Int, header[2])
    fmt = length(header) >= 3 ? parse(Int, header[3]) : 0
    
    has_hedge_weights = fmt >= 10
    has_vtx_weights = (fmt % 10) == 1
    
    hedges = Int[]
    eptr = [1]  # 从 1 开始（Julia 1-based）
    hyperedge_weights = Float64[]
    
    line_idx = 2
    for _ in 1:num_hyperedges
        if line_idx > length(lines)
            error("Not enough hyperedge lines in $filepath. Expected $num_hyperedges hyperedges.")
        end
        parts = split(strip(lines[line_idx]))
        line_idx += 1
        
        if has_hedge_weights
            push!(hyperedge_weights, parse(Float64, parts[1]))
            vertices = [parse(Int, v) for v in parts[2:end]]
        else
            push!(hyperedge_weights, 1.0)
            vertices = [parse(Int, v) for v in parts]
        end
        
        append!(hedges, vertices)
        push!(eptr, length(hedges) + 1)
    end
    
    vertex_weights = if has_vtx_weights
        [parse(Float64, strip(lines[line_idx + i - 1])) for i in 1:num_vertices]
    else
        ones(Float64, num_vertices)
    end
    
    return HypergraphData(num_vertices, num_hyperedges, hedges, eptr, 
                          vertex_weights, hyperedge_weights)
end

function write_hypergraph_hmetis(
    filepath::String,
    hgdata::HypergraphData
)
    """写入 hMETIS 格式的超图文件"""
    has_vtx_weights = any(w != 1.0 for w in hgdata.vertex_weights)
    has_hedge_weights = any(w != 1.0 for w in hgdata.hyperedge_weights)
    
    fmt = (has_hedge_weights ? 10 : 0) + (has_vtx_weights ? 1 : 0)
    
    open(filepath, "w") do f
        if fmt > 0
            println(f, "$(hgdata.num_hyperedges) $(hgdata.num_vertices) $fmt")
        else
            println(f, "$(hgdata.num_hyperedges) $(hgdata.num_vertices)")
        end
        
        # 写入超边
        for i in 1:hgdata.num_hyperedges
            start_idx = hgdata.eptr[i]
            end_idx = hgdata.eptr[i+1] - 1
            hedge_verts = hgdata.hedges[start_idx:end_idx]
            
            if has_hedge_weights
                print(f, "$(hgdata.hyperedge_weights[i]) ")
            end
            println(f, join(hedge_verts, " "))
        end
        
        # 写入顶点权重
        if has_vtx_weights
            for w in hgdata.vertex_weights
                println(f, w)
            end
        end
    end
end

function extract_subhypergraph(
    parent_hgdata::HypergraphData,
    node_indices::Vector{Int}
)
    """提取子超图"""
    node_set = Set(node_indices)
    num_sub_nodes = length(node_indices)
    
    # 创建全局到局部的映射
    global_to_local = Dict{Int, Int}()
    for (local_idx, global_idx) in enumerate(node_indices)
        global_to_local[global_idx] = local_idx
    end
    
    # 提取相关的超边
    sub_hedges = Int[]
    sub_eptr = [1]
    sub_hyperedge_weights = Float64[]
    
    for i in 1:parent_hgdata.num_hyperedges
        start_idx = parent_hgdata.eptr[i]
        end_idx = parent_hgdata.eptr[i+1] - 1
        hedge_verts = parent_hgdata.hedges[start_idx:end_idx]
        
        # 找出在子图中的顶点（转换为局部索引）
        sub_verts = Int[]
        for v in hedge_verts
            if v in node_set
                push!(sub_verts, global_to_local[v])
            end
        end
        
        # 如果超边至少有 2 个顶点在子图中，保留它
        if length(sub_verts) >= 2
            append!(sub_hedges, sub_verts)
            push!(sub_eptr, length(sub_hedges) + 1)
            push!(sub_hyperedge_weights, parent_hgdata.hyperedge_weights[i])
        end
    end
    
    # 提取顶点权重
    sub_vertex_weights = [parent_hgdata.vertex_weights[i] for i in node_indices]
    
    sub_hgdata = HypergraphData(
        num_sub_nodes,
        length(sub_hyperedge_weights),
        sub_hedges,
        sub_eptr,
        sub_vertex_weights,
        sub_hyperedge_weights
    )
    
    return sub_hgdata, global_to_local
end

# ============================================================================
# 递归二分核心逻辑
# ============================================================================

function recursive_bisection(
    hgdata::HypergraphData,
    node_indices::Vector{Int};  # 全局节点索引
    min_cluster_size::Int=50,
    max_depth::Int=10,
    ub_factor::Int=10,
    best_solns::Int=10,
    seed::Int=0,
    verbose::Bool=false,
    current_depth::Int=0,
    work_subdir::String="recursive_work",
    hmetis_exec::String=get(ENV, "HMETIS_EXEC", "hmetis"),
    num_seeds::Int=1
)
    """递归二分聚类（在固定目录运行）"""
    
    num_nodes = hgdata.num_vertices
    
    if verbose
        println("  [Depth $current_depth] Processing $(length(node_indices)) nodes")
    end
    
    # 停止条件
    if num_nodes <= min_cluster_size || current_depth >= max_depth
        if verbose
            reason = num_nodes <= min_cluster_size ? "min_size" : "max_depth"
            println("  [Depth $current_depth] Leaf cluster (reason: $reason)")
        end
        return [node_indices]
    end
    
    # 在 SpecPart 目录下创建工作子目录
    work_dir = joinpath(SPECPART_DIR, work_subdir, "depth_$(current_depth)")
    mkpath(work_dir)

    # [FIX] Use UNIQUE hgr filename per (seed, depth) to avoid race conditions
    # SpectralRefinement.jl extracts basename and writes output to pwd(),
    # so parallel processes using "temp.hgr" would collide.
    unique_hgr_name = "sp_$(seed)_d$(current_depth).hgr"
    temp_hg_file = joinpath(work_dir, unique_hgr_name)
    write_hypergraph_hmetis(temp_hg_file, hgdata)

    if verbose
        println("  [Depth $current_depth] Calling original SpecPart for bisection...")
        println("    Hypergraph: $(hgdata.num_vertices) vertices, $(hgdata.num_hyperedges) hyperedges")
        println("    Working in: $work_dir")
    end

    # ============================================================================
    # [FIX] cd to work_dir so SpectralRefinement writes partition files HERE
    # instead of the shared PROJECT_ROOT/pwd(). This prevents race conditions
    # when multiple Julia processes run in parallel.
    # ============================================================================
    saved_pwd = pwd()
    cd(work_dir)

    partition = Int[]
    try
        best_partition = Int[]
        best_cut = typemax(Int)
        any_trial_ok = false

        for trial in 0:(num_seeds - 1)
            trial_seed = seed + current_depth + trial * 1000003

            # Use unique hgr name per trial to avoid file collisions
            trial_hgr_name = "sp_$(seed)_d$(current_depth)_t$(trial).hgr"
            trial_hg_file = joinpath(work_dir, trial_hgr_name)
            cp(temp_hg_file, trial_hg_file, force=true)

            trial_ok = false
            trial_cut = typemax(Int)
            try
                global_cut, hmetis_cut = SpectralRefinement.SpectralHmetisRefinement(
                    refine_iters=4,
                    solver_iters=20,
                    hg=trial_hg_file,
                    pfile="",
                    fg="",
                    Nparts=2,
                    hyperedges_threshold=900,
                    ub=ub_factor,
                    nev=1,
                    cycles=1,
                    seed=trial_seed,
                    best_solns=best_solns,
                    pseed=trial_seed,
                    hmetis_exec=hmetis_exec
                )
                trial_ok = true
                trial_cut = global_cut

                if verbose
                    println("    [Trial $trial] seed=$trial_seed cutsize=$global_cut (hMETIS: $hmetis_cut)")
                end
            catch e
                @warn "SpecPart trial $trial failed at depth $current_depth (n=$num_nodes): $e"
            end

            if trial_ok
                # Read partition file for this trial
                candidates = [
                    joinpath(work_dir, "$(trial_hgr_name)_$(ub_factor).part.2"),
                    trial_hg_file * ".part.2",
                ]

                partition_file = ""
                for cand in candidates
                    if isfile(cand)
                        partition_file = cand
                        break
                    end
                end

                if !isempty(partition_file)
                    trial_partition = [parse(Int, strip(line)) for line in readlines(partition_file)]
                    if trial_cut < best_cut
                        best_cut = trial_cut
                        best_partition = trial_partition
                        any_trial_ok = true
                    end
                elseif verbose
                    println("    [Trial $trial] Partition file not found, skipping")
                end
            end

            # Clean up trial files
            try
                for f in readdir(work_dir)
                    if startswith(f, "sp_$(seed)_d$(current_depth)_t$(trial)") ||
                       startswith(f, "clustered_")
                        rm(joinpath(work_dir, f), force=true)
                    end
                end
            catch
            end
        end

        if !any_trial_ok
            if verbose
                println("    [Depth $current_depth] All $num_seeds trials failed, returning single cluster")
            end
            return [node_indices]
        end

        if verbose && num_seeds > 1
            println("    [Depth $current_depth] Best cut=$best_cut from $num_seeds trials")
        end

        partition = best_partition
    finally
        # Always restore pwd, even on early return or exception
        cd(saved_pwd)
    end
    # ============================================================================

    # Safety: if partition is empty (shouldn't happen if we reached here), return single cluster
    if isempty(partition)
        return [node_indices]
    end

    # 分割节点到两个子集（使用全局索引）
    part0_nodes_local = findall(p -> p == 0, partition)
    part1_nodes_local = findall(p -> p == 1, partition)
    
    part0_nodes_global = [node_indices[i] for i in part0_nodes_local]
    part1_nodes_global = [node_indices[i] for i in part1_nodes_local]
    
    if verbose
        println("    Part 0: $(length(part0_nodes_global)) nodes")
        println("    Part 1: $(length(part1_nodes_global)) nodes")
    end
    
    # 递归处理两个子分区
    all_clusters = Vector{Vector{Int}}()
    
    for (part_id, part_nodes) in enumerate([part0_nodes_global, part1_nodes_global])
        if length(part_nodes) == 0
            continue
        end
        
        if length(part_nodes) <= min_cluster_size || current_depth + 1 >= max_depth
            # 直接作为叶子簇
            push!(all_clusters, part_nodes)
        else
            # 提取子超图
            local_indices_in_current = Int[]
            current_global_to_local = Dict(g => l for (l, g) in enumerate(node_indices))
            for global_idx in part_nodes
                if haskey(current_global_to_local, global_idx)
                    push!(local_indices_in_current, current_global_to_local[global_idx])
                end
            end
            
            sub_hgdata, _ = extract_subhypergraph(hgdata, local_indices_in_current)
            
            # 递归调用
            sub_clusters = recursive_bisection(
                sub_hgdata,
                part_nodes;
                min_cluster_size=min_cluster_size,
                max_depth=max_depth,
                ub_factor=ub_factor,
                best_solns=best_solns,
                seed=seed,
                verbose=verbose,
                current_depth=current_depth + 1,
                work_subdir=work_subdir,
                hmetis_exec=hmetis_exec,
                num_seeds=num_seeds
            )
            
            append!(all_clusters, sub_clusters)
        end
    end
    
    return all_clusters
end

# ============================================================================
# 命令行参数解析
# ============================================================================

function parse_commandline()
    s = ArgParseSettings()

    @add_arg_table! s begin
        "--hgr"
            help = "Input hMETIS hypergraph file"
            default = ""
        "--features"
            help = "Input GIFT features file (not used)"
            default = ""
        "--output"
            help = "Output JSON file"
            default = ""
        "--ub"
            help = "Unbalance factor"
            arg_type = Int
            default = 10
        "--best_solns"
            help = "Number of best solutions"
            arg_type = Int
            default = 10
        "--hmetis_path"
            help = "Absolute path to hmetis executable (supports seed)"
            default = get(ENV, "HMETIS_EXEC", "hmetis")
        "--seed"
            help = "Random seed"
            arg_type = Int
            default = 0
        "--recursive"
            help = "Enable recursive bisection (always enabled)"
            action = :store_true
        "--min_cluster_size"
            help = "Min cluster size"
            arg_type = Int
            default = 50
        "--max_depth"
            help = "Max recursion depth"
            arg_type = Int
            default = 10
        "--verbose"
            help = "Verbose"
            action = :store_true
        "--batch"
            help = "Path to JSON manifest for batch mode"
            default = ""
        "--num_seeds"
            help = "Number of seeds per bisection level"
            arg_type = Int
            default = 1
    end

    return parse_args(s)
end

# ============================================================================
# 主函数
# ============================================================================

function main()
    args = parse_commandline()
    
    if args["verbose"]
        println("="^60)
        println("SpecPart Recursive Wrapper (In-place)")
        println("Working in: $SPECPART_DIR")
        println("="^60)
        println("hgr: ", args["hgr"])
        println("output: ", args["output"])
        println("ub: ", args["ub"])
        println("best_solns: ", args["best_solns"])
        println("seed: ", args["seed"])
        println("hmetis_path: ", args["hmetis_path"])
        println("min_cluster_size: ", args["min_cluster_size"])
        println("max_depth: ", args["max_depth"])
        println("="^60)
    end
    
    # 复制输入文件到 SpecPart 目录（如果不在该目录）
    input_hgr = args["hgr"]
    if !startswith(abspath(input_hgr), SPECPART_DIR)
        # 使用时间戳和种子创建唯一的文件名
        timestamp = replace(string(now()), ":" => "-", "." => "-")
        unique_name = "input_$(args["seed"])_$(timestamp).hgr"
        local_hgr = joinpath(SPECPART_DIR, unique_name)
        
        # 复制文件
        try
            cp(input_hgr, local_hgr, force=true)
            if args["verbose"]
                println("\nCopied input file to: $local_hgr")
            end
        catch e
            @error "Failed to copy input file: $e"
            rethrow(e)
        end
        
        # 验证复制的文件不是空的
        if filesize(local_hgr) == 0
            @error "Copied file is empty: $local_hgr (original: $input_hgr, size: $(filesize(input_hgr)))"
            error("File copy failed: copied file is empty")
        end
        
        input_hgr = local_hgr
    end
    
    # 读取输入超图
    hgdata = read_hypergraph_hmetis(input_hgr)
    
    if args["verbose"]
        println("\nInput hypergraph:")
        println("  Vertices: ", hgdata.num_vertices)
        println("  Hyperedges: ", hgdata.num_hyperedges)
    end
    
    # 初始节点索引（全局）
    initial_nodes = collect(1:hgdata.num_vertices)
    
    # 递归二分
    if args["verbose"]
        println("\nStarting recursive bisection...")
    end
    
    # 创建工作目录
    work_subdir = "recursive_work_$(args["seed"])"
    
    clusters = recursive_bisection(
        hgdata,
        initial_nodes;
        min_cluster_size=args["min_cluster_size"],
        max_depth=args["max_depth"],
        ub_factor=args["ub"],
        best_solns=args["best_solns"],
        seed=args["seed"],
        verbose=args["verbose"],
        work_subdir=work_subdir,
        hmetis_exec=args["hmetis_path"],
        num_seeds=args["num_seeds"]
    )
    
    # 清理工作目录
    work_dir = joinpath(SPECPART_DIR, work_subdir)
    try
        rm(work_dir, recursive=true, force=true)
        if args["verbose"]
            println("\nCleaned up work directory: $work_dir")
        end
    catch
    end
    
    # 清理复制的输入文件（如果有）
    if !startswith(abspath(args["hgr"]), SPECPART_DIR) && isfile(input_hgr)
        try
            rm(input_hgr, force=true)
            if args["verbose"]
                println("Cleaned up copied input file: $input_hgr")
            end
        catch
        end
    end
    
    if args["verbose"]
        println("\nComplete! Generated $(length(clusters)) clusters")
        sizes = [length(c) for c in clusters]
        println("Cluster sizes: min=$(minimum(sizes)), median=$(median(sizes)), max=$(maximum(sizes))")
    end
    
    # 构建 cluster_map（0-based cluster ID）
    cluster_map = zeros(Int, hgdata.num_vertices)
    for (cid, cluster) in enumerate(clusters)
        for node in cluster
            cluster_map[node] = cid - 1
        end
    end
    
    # 输出
    output_data = Dict(
        "clusters" => clusters,
        "cluster_map" => cluster_map,
        "stats" => Dict("num_clusters" => length(clusters))
    )
    
    open(args["output"], "w") do f
        JSON.print(f, output_data, 2)
    end
    
    if args["verbose"]
        println("\nOutput written to: ", args["output"])
        println("="^60)
    end
end

# ============================================================================
# Batch mode: process multiple clusters in a single Julia session
# ============================================================================

function process_single_job(job, verbose::Bool)
    # Process one cluster job from a batch manifest entry.
    hgr_path = job["hgr_path"]
    output_path = job["output_path"]
    seed = get(job, "seed", 0)
    min_cluster_size = get(job, "min_cluster_size", 50)
    max_depth = get(job, "max_depth", 10)
    ub_factor = get(job, "ub", 10)
    best_solns = get(job, "best_solns", 10)
    hmetis_exec = get(job, "hmetis_path",
        get(ENV, "HMETIS_EXEC", "hmetis"))
    num_seeds = get(job, "num_seeds", 1)

    if !isfile(hgr_path)
        @warn "Batch job: hgr file not found, skipping: $hgr_path"
        # Write empty result so Python side knows it failed
        open(output_path, "w") do f
            JSON.print(f, Dict("clusters" => [], "cluster_map" => [], "stats" => Dict("num_clusters" => 0, "error" => "hgr not found")), 2)
        end
        return
    end

    # Copy to SpecPart dir if needed
    input_hgr = hgr_path
    local_hgr = ""
    if !startswith(abspath(hgr_path), SPECPART_DIR)
        unique_name = "batch_$(seed)_$(hash(hgr_path)).hgr"
        local_hgr = joinpath(SPECPART_DIR, unique_name)
        try
            cp(hgr_path, local_hgr, force=true)
        catch e
            @warn "Batch job: failed to copy $hgr_path: $e"
            open(output_path, "w") do f
                JSON.print(f, Dict("clusters" => [], "cluster_map" => [], "stats" => Dict("num_clusters" => 0, "error" => string(e))), 2)
            end
            return
        end
        input_hgr = local_hgr
    end

    try
        hgdata = read_hypergraph_hmetis(input_hgr)
        initial_nodes = collect(1:hgdata.num_vertices)
        work_subdir = "recursive_work_batch_$(seed)_$(hash(hgr_path))"

        clusters = recursive_bisection(
            hgdata,
            initial_nodes;
            min_cluster_size=min_cluster_size,
            max_depth=max_depth,
            ub_factor=ub_factor,
            best_solns=best_solns,
            seed=seed,
            verbose=verbose,
            work_subdir=work_subdir,
            hmetis_exec=hmetis_exec,
            num_seeds=num_seeds
        )
        try rm(work_dir, recursive=true, force=true) catch end

        # Build cluster_map (0-based)
        cluster_map = zeros(Int, hgdata.num_vertices)
        for (cid, cluster) in enumerate(clusters)
            for node in cluster
                cluster_map[node] = cid - 1
            end
        end

        output_data = Dict(
            "clusters" => clusters,
            "cluster_map" => cluster_map,
            "stats" => Dict("num_clusters" => length(clusters))
        )

        open(output_path, "w") do f
            JSON.print(f, output_data, 2)
        end

        if verbose
            println("  [Batch] Processed $(hgdata.num_vertices) nodes -> $(length(clusters)) clusters: $output_path")
        end
    catch e
        @warn "Batch job failed for $hgr_path: $e"
        open(output_path, "w") do f
            JSON.print(f, Dict("clusters" => [], "cluster_map" => [], "stats" => Dict("num_clusters" => 0, "error" => string(e))), 2)
        end
    finally
        # Clean up copied input
        if !isempty(local_hgr) && isfile(local_hgr)
            try rm(local_hgr, force=true) catch end
        end
    end
end

function batch_main(manifest_path::String, verbose::Bool)
    # Process a batch manifest JSON file containing multiple cluster jobs.
    if !isfile(manifest_path)
        error("Batch manifest not found: $manifest_path")
    end

    manifest = JSON.parsefile(manifest_path)
    jobs = manifest["jobs"]
    println("[Batch] Processing $(length(jobs)) jobs from $manifest_path")

    for (i, job) in enumerate(jobs)
        if verbose
            println("[Batch] Job $i/$(length(jobs)): $(get(job, "hgr_path", "?"))")
        end
        process_single_job(job, verbose)
    end

    println("[Batch] All $(length(jobs)) jobs completed.")
end

# 运行主函数
if abspath(PROGRAM_FILE) == @__FILE__
    args = parse_commandline()
    if !isempty(args["batch"])
        batch_main(args["batch"], args["verbose"])
    else
        main()
    end
end
