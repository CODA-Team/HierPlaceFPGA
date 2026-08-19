#!/usr/bin/env julia

using Printf
using Dates
using Random

include("SpectralRefinement.jl")

const PROJECT_ROOT = dirname(@__DIR__)
const OPENROAD = get(
    ENV,
    "SPECPART_OPENROAD_BIN",
    joinpath(PROJECT_ROOT, "TritonPart", "build", "src", "openroad"),
)
const READLINE_LIB = get(ENV, "SPECPART_READLINE_LIB", "")
const OPENROAD_LIBRARY_PATH = get(ENV, "SPECPART_OPENROAD_LIBRARY_PATH", "")
const OPENROAD_LAUNCHER = get(ENV, "SPECPART_OPENROAD_LAUNCHER", "")

function preload_hypergraph(hg_file::String)
    (hedges, eptr, vertex_weights, hyperedge_weights, num_vertices, num_hyperedges, ~) =
        Main.SpectralRefinement.ReadHypergraphFile(hg_file)

    hypergraph = Main.SpectralRefinement.Hypergraph(
        num_vertices,
        num_hyperedges,
        hedges,
        eptr,
        vertex_weights,
        hyperedge_weights,
    )

    (hypergraph_processed, _, new_indices, _) = Main.SpectralRefinement.IsolateIslands(hypergraph)
    incidence_struct = Main.SpectralRefinement.HypergraphToIncidence(hypergraph_processed)
    return hypergraph_processed, incidence_struct, new_indices
end

function invoke_tritonpart(hg_file::String, ub_factor::Int, seed::Int, tcl_dir::String, tag::String)
    tcl_file = joinpath(tcl_dir, "$(tag).tcl")
    open(tcl_file, "w") do f
        println(f, "triton_part_hypergraph \\")
        println(f, "  -hypergraph_file {$hg_file} \\")
        println(f, "  -num_parts 2 \\")
        println(f, "  -balance_constraint $ub_factor \\")
        println(f, "  -seed $seed \\")
        println(f, "  -num_best_initial_solutions 10 \\")
        println(f, "  -num_coarsen_solutions 3 \\")
        println(f, "  -thr_coarsen_hyperedge_size_skip 200 \\")
        println(f, "  -thr_coarsen_vertices 10 \\")
        println(f, "  -thr_coarsen_hyperedges 50 \\")
        println(f, "  -coarsening_ratio 1.6 \\")
        println(f, "  -max_coarsen_iters 30 \\")
        println(f, "  -refiner_iters 10 \\")
        println(f, "  -max_moves 100 \\")
        println(f, "  -early_stop_ratio 0.5 \\")
        println(f, "  -v_cycle_flag true \\")
        println(f, "  -max_num_vcycle 3")
        println(f, "exit")
    end

    output = ""
    try
        env_vars = copy(ENV)
        if !isempty(READLINE_LIB)
            env_vars["LD_PRELOAD"] = READLINE_LIB
        end
        if !isempty(OPENROAD_LIBRARY_PATH)
            env_vars["LD_LIBRARY_PATH"] = OPENROAD_LIBRARY_PATH
        end
        openroad_cmd = isempty(OPENROAD_LAUNCHER) ?
            `$OPENROAD -no_init -exit $tcl_file` :
            `$OPENROAD_LAUNCHER $OPENROAD $tcl_file`
        output = read(setenv(openroad_cmd, env_vars), String)
    catch e
        println("  TritonPart 调用错误: $e")
    end
    rm(tcl_file, force=true)
    return output
end

function make_seed_list(base_seed::Int, num_seeds::Int)
    return [base_seed + (i - 1) * 200 for i in 1:num_seeds]
end

function make_safe_output_dir(requested_dir::String)
    if !isdir(requested_dir)
        mkpath(requested_dir)
        return requested_dir
    end
    if isempty(readdir(requested_dir))
        return requested_dir
    end
    parent_dir = dirname(requested_dir)
    base_name = basename(requested_dir)
    ts = Dates.format(now(), "yyyymmdd_HHMMSS")
    actual_dir = joinpath(parent_dir, "$(base_name)_$(ts)")
    mkpath(actual_dir)
    println("输出目录非空，改写到: $actual_dir")
    return actual_dir
end

function balance_bounds(total_weight::Int, ub_factor::Int)
    min_capacity = floor(Int, total_weight * (50 - ub_factor) / 100)
    max_capacity = ceil(Int, total_weight * (50 + ub_factor) / 100)
    return min_capacity, max_capacity
end

function is_balance_ok(part_area::Vector{Int}, ub_factor::Int)
    total_weight = sum(part_area)
    min_capacity, max_capacity = balance_bounds(total_weight, ub_factor)
    return all(a -> min_capacity <= a <= max_capacity, part_area), min_capacity, max_capacity
end

function load_projected_partition(
    part_file::String,
    new_indices::Vector{Int},
    num_vertices::Int,
    num_processed_vertices::Int,
)
    final_part = zeros(Int, num_vertices)
    i = 0
    open(part_file, "r") do f
        for ln in eachline(f)
            s = strip(ln)
            isempty(s) && continue
            i += 1
            if i > num_vertices
                println("    警告: $part_file 行数超过原图顶点数 $(num_vertices)，额外行将被忽略")
                break
            end
            final_part[i] = parse(Int, s)
        end
    end

    if i < num_vertices
        println("    警告: $part_file 仅有 $i 行，少于原图顶点数 $(num_vertices)；缺失顶点默认保留为 0")
    end

    projected = zeros(Int, num_processed_vertices)
    for v in 1:min(length(new_indices), num_vertices)
        cc = new_indices[v]
        if cc == 0
            continue
        end
        projected[cc] = final_part[v]
    end
    return projected
end

function compact_processed_hypergraph(hypergraph_processed, original_indices, new_indices, unused_indices)
    active_vertices = sort(unique(hypergraph_processed.hedges))
    if length(active_vertices) == hypergraph_processed.n
        return hypergraph_processed, original_indices, new_indices, unused_indices
    end

    old_to_new = zeros(Int, hypergraph_processed.n)
    for (new_v, old_v) in enumerate(active_vertices)
        old_to_new[old_v] = new_v
    end

    compact_hedges = old_to_new[hypergraph_processed.hedges]
    compact_vwts = hypergraph_processed.vwts[active_vertices]
    compact_hg = Main.SpectralRefinement.Hypergraph(
        length(active_vertices),
        hypergraph_processed.e,
        compact_hedges,
        hypergraph_processed.eptr,
        compact_vwts,
        hypergraph_processed.hwts,
    )

    compact_original_indices = original_indices[active_vertices]
    inactive_vertices = setdiff(collect(1:hypergraph_processed.n), active_vertices)
    compact_unused_indices = vcat(unused_indices, original_indices[inactive_vertices])

    compact_new_indices = zeros(Int, length(new_indices))
    for (new_v, old_v) in enumerate(active_vertices)
        orig_v = original_indices[old_v]
        compact_new_indices[orig_v] = new_v
    end

    println("    compact processed hypergraph: $(hypergraph_processed.n) -> $(compact_hg.n) vertices")
    return compact_hg, compact_original_indices, compact_new_indices, compact_unused_indices
end

function parse_best_csv(csv_file::String)
    rows = Dict{Int, Dict{String, String}}()
    open(csv_file, "r") do f
        header = split(chomp(readline(f)), ",")
        for ln in eachline(f)
            vals = split(chomp(ln), ",")
            row = Dict{String, String}()
            for (h, v) in zip(header, vals)
                row[h] = v
            end
            rows[parse(Int, row["ub_factor"])] = row
        end
    end
    return rows
end

function build_original_overlay_part_files(parts_dir::AbstractString, ub2::AbstractString)
    seed_list = [100, 300, 500, 700, 900]
    part_files = String[]
    for seed in seed_list
        part_file = joinpath(parts_dir, "guided_ub$(ub2)_seed$(seed).part.2")
        if !isfile(part_file)
            return String[]
        end
        push!(part_files, part_file)
    end
    return part_files
end

function run_cutoverlay(hg_file::String, part_files::Vector{String}, final_ub::Int,
                        seeds::Vector{Int}, output_dir::String, final_part_path::String)
    t_overlay_build = time()
    hg_name = split(hg_file, "/")[end]
    hg_name_clustered = "clustered_" * hg_name

    (hedges, eptr, vertex_weights, hyperedge_weights, num_vertices, num_hyperedges, ~) =
        Main.SpectralRefinement.ReadHypergraphFile(hg_file)

    fixed_vtxs = -ones(Int, num_vertices)
    hypergraph = Main.SpectralRefinement.Hypergraph(num_vertices, num_hyperedges, hedges, eptr,
                                                    vertex_weights, hyperedge_weights)

    (hypergraph_processed, original_indices, new_indices, unused_indices) =
        Main.SpectralRefinement.IsolateIslands(hypergraph)

    fixed_vtxs_processed = fixed_vtxs[original_indices]
    incidence_struct = Main.SpectralRefinement.HypergraphToIncidence(hypergraph_processed)
    incidence_list = Main.SpectralRefinement.GenerateIncidenceList(incidence_struct)
    hyperedge_pair_list = Main.SpectralRefinement.GenerateHypergraphPairList(hypergraph_processed)
    hyperedges_hash = Main.SpectralRefinement.GenerateHyperedgesHash(hypergraph_processed)
    fixed_vertex_flag = maximum(fixed_vtxs_processed) > -1 ? true : false
    community = ones(Int, hypergraph_processed.n)

    hypergraph_c = Main.SpectralRefinement.Hypergraph_C(
        hypergraph_processed,
        incidence_list,
        hyperedge_pair_list,
        community,
        fixed_vtxs_processed,
        fixed_vertex_flag,
        hyperedges_hash,
    )

    partition_matrix = zeros(Int, length(part_files), hypergraph_processed.n)
    for i in 1:length(part_files)
        partition_matrix[i, :] = load_projected_partition(
            part_files[i],
            new_indices,
            num_vertices,
            hypergraph_processed.n,
        )
    end

    Random.seed!(1200)

    (hypergraph_clustered, incidence_struct_clustered, fixed_part_clustered, ~, cclist, ~) =
        Main.SpectralRefinement.GenerateSpectralCommunities(partition_matrix, hypergraph_c, incidence_struct)

    Main.SpectralRefinement.ExportHypergraph(hypergraph_clustered, hg_name_clustered, fixed_part_clustered)
    overlay_build_elapsed = round(time() - t_overlay_build, digits=3)

    best_cut = typemax(Int)
    best_seed = -1
    best_clustered_cut = -1
    best_final_part = Int[]
    best_seed_elapsed = Inf
    seed_records = []

    for seed in seeds
        t_seed = time()
        tag = "cutoverlay_final_ub$(lpad(string(final_ub), 2, '0'))_seed$(seed)"
        invoke_tritonpart(hg_name_clustered, final_ub, seed, output_dir, tag)

        pname = hg_name_clustered * ".part.2"
        partition_vector = zeros(Int, hypergraph_clustered.n)
        if !isfile(pname)
            println("    警告: seed=$seed 未生成 $pname")
            seed_elapsed = round(time() - t_seed, digits=3)
            push!(seed_records, (
                ub=final_ub, seed=seed, clustered_cut=-1, final_cut=-1,
                balance_ok=false, part_area0=-1, part_area1=-1,
                min_capacity=-1, max_capacity=-1, elapsed_sec=seed_elapsed
            ))
            continue
        end

        open(pname, "r") do f
            k = 0
            for ln in eachline(f)
                k += 1
                if k > length(partition_vector)
                    println("    警告: $pname 行数超过 clustered graph 顶点数 $(length(partition_vector))，额外行将被忽略")
                    break
                end
                partition_vector[k] = parse(Int, ln)
            end
        end
        rm(pname, force=true)

        post_tool_cut = Main.SpectralRefinement.findCutsize(partition_vector, hypergraph_clustered, incidence_struct_clustered)

        partition_vector_top = zeros(Int, hypergraph_processed.n)
        for i in 1:length(cclist)
            partition_vector_top[i] = partition_vector[cclist[i]]
        end

        final_part = zeros(Int, num_vertices)
        part_area = [0, 0]

        for i in 1:length(original_indices)
            v = original_indices[i]
            final_part[v] = partition_vector_top[i]
            part_area[final_part[v] + 1] += hypergraph.vwts[v]
        end

        for i in 1:length(unused_indices)
            v = unused_indices[i]
            min_side = part_area[1] < part_area[2] ? 1 : 2
            final_part[v] = min_side - 1
            part_area[min_side] += vertex_weights[v]
        end

        balance_ok, min_capacity, max_capacity = is_balance_ok(part_area, final_ub)

        # Match the original cut-overlay script: evaluate on the processed graph.
        # Building incidence for the raw Titan graph can fail when isolated
        # vertex ids are absent from the sorted incidence representation.
        cut_size = Main.SpectralRefinement.findCutsize(partition_vector_top, hypergraph_processed, incidence_struct)
        seed_elapsed = round(time() - t_seed, digits=3)
        println(
            "    seed=$seed clustered_cut=$post_tool_cut final_cut=$cut_size " *
            "part_area=$(part_area[1]):$(part_area[2]) balance_ok=$balance_ok " *
            "capacity=[$min_capacity,$max_capacity] elapsed_sec=$seed_elapsed"
        )
        push!(seed_records, (
            ub=final_ub, seed=seed, clustered_cut=post_tool_cut, final_cut=cut_size,
            balance_ok=balance_ok, part_area0=part_area[1], part_area1=part_area[2],
            min_capacity=min_capacity, max_capacity=max_capacity, elapsed_sec=seed_elapsed
        ))

        if balance_ok && cut_size > 0 &&
           (cut_size < best_cut || (cut_size == best_cut && seed_elapsed < best_seed_elapsed))
            best_cut = cut_size
            best_seed = seed
            best_clustered_cut = post_tool_cut
            best_final_part = copy(final_part)
            best_seed_elapsed = seed_elapsed
        end
    end

    rm(hg_name_clustered, force=true)

    seed_detail_csv = joinpath(output_dir, "cutoverlay_final_seed_details.csv")
    need_header = !isfile(seed_detail_csv)
    open(seed_detail_csv, "a") do f
        if need_header
            println(f, "ub,seed,clustered_cut,final_cut,balance_ok,part_area0,part_area1,min_capacity,max_capacity,elapsed_sec,selected")
        end
        for r in seed_records
            selected = (r.seed == best_seed && r.final_cut == best_cut)
            println(
                f,
                "$(r.ub),$(r.seed),$(r.clustered_cut),$(r.final_cut),$(r.balance_ok),$(r.part_area0),$(r.part_area1),$(r.min_capacity),$(r.max_capacity),$(r.elapsed_sec),$(selected)"
            )
        end
    end

    if best_seed < 0
        println("    警告: 所有 seed 都失败")
        return (-1, -1, overlay_build_elapsed, 0.0)
    end

    open(final_part_path, "w") do f
        for i in 1:length(best_final_part)
            println(f, best_final_part[i])
        end
    end

    println(
        "    best_seed=$best_seed clustered_cut=$best_clustered_cut final_cut=$best_cut " *
        "overlay_build_elapsed_sec=$overlay_build_elapsed best_seed_elapsed_sec=$best_seed_elapsed " *
        "saved_part=$final_part_path"
    )
    return (best_cut, best_seed, overlay_build_elapsed, best_seed_elapsed)
end

function choose_best_row(exp_dirs::Vector{String}, ub::Int)
    best = nothing
    for exp_dir in exp_dirs
        csv_file = joinpath(exp_dir, "ub_sweep_compare_with_inference_multiseed_best.csv")
        if !isfile(csv_file)
            continue
        end
        rows = parse_best_csv(csv_file)
        haskey(rows, ub) || continue
        row = rows[ub]
        guided_cut = parse(Int, row["guided_best_cutsize"])
        baseline_cut = parse(Int, row["baseline_best_cutsize"])
        candidate = (
            exp_dir = exp_dir,
            row = row,
            guided_cut = guided_cut,
            baseline_cut = baseline_cut,
        )
        if best === nothing ||
           candidate.guided_cut < best.guided_cut ||
           (candidate.guided_cut == best.guided_cut && candidate.baseline_cut < best.baseline_cut)
            best = candidate
        end
    end
    return best
end

function run_case(
    bench_name::AbstractString,
    hgr_file::AbstractString,
    requested_out_dir::AbstractString,
    base_seed::Int,
    exp_dirs::Vector{<:AbstractString};
    ub_start::Int = 1,
    ub_end::Int = 20,
    num_seeds::Int = 5,
)
    if length(exp_dirs) < 2
        println("至少需要两个实验目录")
        return
    end

    out_dir = make_safe_output_dir(requested_out_dir)
    mkpath(out_dir)
    parts_out = joinpath(out_dir, "parts")
    logs_out = joinpath(out_dir, "logs")
    mkpath(parts_out)
    mkpath(logs_out)

    hypergraph, incidence_struct, new_indices = preload_hypergraph(hgr_file)
    seeds = make_seed_list(base_seed, num_seeds)
    println("benchmark=$bench_name")
    println("experiments=" * join(exp_dirs, ", "))
    println("最终 TritonPart seeds: $(join(seeds, ","))")

    results = []
    for ub in ub_start:ub_end
        t_ub = time()
        chosen = choose_best_row(exp_dirs, ub)
        ub2 = lpad(string(ub), 2, '0')
        println("UB=$ub")

        if chosen === nothing
            println("  没有找到可用实验记录，跳过")
            elapsed_ub = round(time() - t_ub, digits=3)
            push!(results, (
                ub=ub, cutsize=-1, best_seed=-1, source_exp="", guided_best_cut=-1,
                baseline_part="", guided_part="", final_part="", cutoverlay_elapsed_sec=elapsed_ub,
                overlay_build_elapsed_sec=0.0, best_seed_elapsed_sec=0.0
            ))
            continue
        end

        row = chosen.row
        source_exp = chosen.exp_dir
        parts_dir = joinpath(source_exp, "parts")
        guided_seed = row["guided_best_seed"]
        baseline_seed = row["baseline_best_seed"]
        guided_part = joinpath(parts_dir, "guided_ub$(ub2)_seed$(guided_seed).part.2")
        baseline_part = joinpath(parts_dir, "baseline_ub$(ub2)_seed$(baseline_seed).part.2")

        println("  source_exp=$source_exp")
        println("  guided_best_cut=$(chosen.guided_cut)")
        println("  guided_part=$guided_part")
        println("  baseline_part=$baseline_part")

        if !isfile(guided_part) || !isfile(baseline_part)
            println("  缺少 part 文件，跳过")
            elapsed_ub = round(time() - t_ub, digits=3)
            push!(results, (
                ub=ub, cutsize=-1, best_seed=-1, source_exp=source_exp,
                guided_best_cut=chosen.guided_cut, baseline_part=baseline_part,
                guided_part=guided_part, final_part="", cutoverlay_elapsed_sec=elapsed_ub,
                overlay_build_elapsed_sec=0.0, best_seed_elapsed_sec=0.0
            ))
            continue
        end

        overlay_part_files = build_original_overlay_part_files(parts_dir, ub2)
        if isempty(overlay_part_files)
            println("  缺少 5 个 guided seed part，回退到 baseline_best + guided_best")
            overlay_part_files = [baseline_part, guided_part]
        else
            println("  original-style overlay parts=$(length(overlay_part_files))")
        end

        saved_part = joinpath(parts_out, "cutoverlay_ub$(ub2).part.2")
        cut, best_seed, overlay_build_elapsed, best_seed_elapsed =
            run_cutoverlay(hgr_file, overlay_part_files, ub, seeds, out_dir, saved_part)
        elapsed_ub = round(time() - t_ub, digits=3)

        println(
            "  cutoverlay_cut=$cut best_seed=$best_seed elapsed_sec=$elapsed_ub " *
            "overlay_build_elapsed_sec=$overlay_build_elapsed best_seed_elapsed_sec=$best_seed_elapsed"
        )
        push!(results, (
            ub=ub, cutsize=cut, best_seed=best_seed, source_exp=source_exp,
            guided_best_cut=chosen.guided_cut, baseline_part=baseline_part,
            guided_part=guided_part, final_part=saved_part, cutoverlay_elapsed_sec=elapsed_ub,
            overlay_build_elapsed_sec=overlay_build_elapsed, best_seed_elapsed_sec=best_seed_elapsed
        ))
    end

    out_csv = joinpath(out_dir, "cutoverlay_best_guided_across_experiments.csv")
    open(out_csv, "w") do f
        println(f, "ub,cutoverlay_cutsize,best_seed,source_exp,guided_best_cut,cutoverlay_elapsed_sec,overlay_build_elapsed_sec,best_seed_elapsed_sec,baseline_part,guided_part,final_part")
        for r in results
            println(
                f,
                "$(r.ub),$(r.cutsize),$(r.best_seed),$(r.source_exp),$(r.guided_best_cut),$(r.cutoverlay_elapsed_sec),$(r.overlay_build_elapsed_sec),$(r.best_seed_elapsed_sec),$(r.baseline_part),$(r.guided_part),$(r.final_part)"
            )
        end
    end

    println("结果已保存到: $out_csv")
end

function main()
    if length(ARGS) < 5
        println("用法:")
        println("  julia run_cutoverlay_from_best_guided_across_experiments.jl <benchmark_name> <hgr_file> <out_dir> <base_seed> <exp_dir1> <exp_dir2> [exp_dir3 ...]")
        println("可选: [ub_start] [ub_end] [num_seeds]，以 key=value 方式传入")
        return
    end

    bench_name = ARGS[1]
    hgr_file = ARGS[2]
    requested_out_dir = ARGS[3]
    base_seed = parse(Int, ARGS[4])

    positional = String[]
    opts = Dict{String, String}()
    for arg in ARGS[5:end]
        if occursin("=", arg)
            k, v = split(arg, "=", limit=2)
            opts[k] = v
        else
            push!(positional, arg)
        end
    end

    exp_dirs = positional
    ub_start = parse(Int, get(opts, "ub_start", "1"))
    ub_end = parse(Int, get(opts, "ub_end", "20"))
    num_seeds = parse(Int, get(opts, "num_seeds", "5"))
    run_case(
        bench_name,
        hgr_file,
        requested_out_dir,
        base_seed,
        exp_dirs;
        ub_start=ub_start,
        ub_end=ub_end,
        num_seeds=num_seeds,
    )
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
