#!/usr/bin/env julia

using Dates

function include_cutoverlay_core()
    core_file = joinpath(@__DIR__, "run_cutoverlay_from_best_guided_across_experiments.jl")
    Base.include(Main, core_file)
end

include_cutoverlay_core()

function parse_named_args(args)
    opts = Dict{String, String}()
    for arg in args
        occursin("=", arg) || error("参数必须使用 key=value 格式: $arg")
        key, value = split(arg, "=", limit=2)
        opts[String(key)] = String(value)
    end
    return opts
end

function required_arg(opts::Dict{String, String}, key::String)
    haskey(opts, key) || error("缺少必要参数: $key")
    isempty(opts[key]) && error("参数不能为空: $key")
    return opts[key]
end

function find_guided_best_solution(exp_dir::String, ub::Int)
    csv_file = joinpath(exp_dir, "ub_sweep_compare_with_inference_multiseed_best.csv")
    isfile(csv_file) || error("找不到实验汇总 CSV: $csv_file")

    rows = parse_best_csv(csv_file)
    haskey(rows, ub) || error("CSV 中没有 UB=$(ub): $(csv_file)")
    row = rows[ub]

    ub2 = lpad(string(ub), 2, '0')
    for field in ("guided_best_seed", "guided_best_cutsize")
        haskey(row, field) || error("CSV 缺少字段 $(field): $(csv_file)")
        isempty(strip(row[field])) &&
            error(
                "CSV 字段 $(field) 为空（UB=$(ub)）: $(csv_file)；" *
                "请检查该实验的 guided_ub$(ub2)_seed*.log，通常是 OpenROAD 启动失败",
            )
    end
    seed = strip(row["guided_best_seed"])
    guided_cut = tryparse(Int, strip(row["guided_best_cutsize"]))
    guided_cut === nothing &&
        error("guided_best_cutsize 不是整数: $(row["guided_best_cutsize"])，CSV=$(csv_file)")
    part_file = joinpath(exp_dir, "parts", "guided_ub$(ub2)_seed$(seed).part.2")
    isfile(part_file) || error("找不到 guided best solution: $(part_file)")

    return (
        exp_dir=exp_dir,
        seed=seed,
        guided_cut=guided_cut,
        part_file=part_file,
    )
end

function calculate_final_seed_statistics(csv_file::String, ub::Int)
    isfile(csv_file) || error("找不到 Cut-Overlay seed 明细 CSV: $(csv_file)")
    lines = readlines(csv_file)
    isempty(lines) && error("Cut-Overlay seed 明细 CSV 为空: $(csv_file)")

    header = split(chomp(lines[1]), ",")
    column_index = Dict(name => index for (index, name) in enumerate(header))
    for field in ("ub", "final_cut", "balance_ok")
        haskey(column_index, field) ||
            error("Cut-Overlay seed 明细 CSV 缺少字段 $(field): $(csv_file)")
    end

    total_seed_count = 0
    valid_cuts = Int[]
    for line in lines[2:end]
        isempty(strip(line)) && continue
        values = split(chomp(line), ",", keepempty=true)
        length(values) == length(header) ||
            error("Cut-Overlay seed 明细 CSV 行字段数量不正确: $(line)")

        row_ub = tryparse(Int, strip(values[column_index["ub"]]))
        row_ub == ub || continue
        total_seed_count += 1

        final_cut = tryparse(Int, strip(values[column_index["final_cut"]]))
        balance_ok = lowercase(strip(values[column_index["balance_ok"]])) == "true"
        if final_cut !== nothing && final_cut > 0 && balance_ok
            push!(valid_cuts, final_cut)
        end
    end

    isempty(valid_cuts) &&
        error("UB=$(ub) 没有成功且满足平衡约束的 Cut-Overlay seed 结果")
    # Cut 均为正整数；这里使用四舍五入得到整数平均 Cut。
    mean_final_cut =
        div(sum(valid_cuts) + div(length(valid_cuts), 2), length(valid_cuts))
    return (
        mean_final_cut=mean_final_cut,
        valid_seed_count=length(valid_cuts),
        total_seed_count=total_seed_count,
    )
end

function main()
    opts = parse_named_args(ARGS)
    benchmark = required_arg(opts, "benchmark")
    hgr_file = abspath(required_arg(opts, "hgr_file"))
    requested_out_dir = abspath(required_arg(opts, "out_dir"))
    exp_dirs = split(required_arg(opts, "exp_dirs"), ";")
    ub = parse(Int, required_arg(opts, "ub"))
    base_seed = parse(Int, get(opts, "base_seed", "100"))
    num_seeds = parse(Int, get(opts, "num_seeds", "5"))

    isfile(hgr_file) || error("找不到 HGR 文件: $hgr_file")
    length(exp_dirs) == 3 ||
        error("必须提供恰好 3 个实验目录，当前数量=$(length(exp_dirs))")
    1 <= ub <= 49 || error("UB 必须在 1 到 49 之间，当前 UB=$ub")
    num_seeds >= 1 || error("num_seeds 必须大于等于 1")

    solutions = [find_guided_best_solution(abspath(exp_dir), ub) for exp_dir in exp_dirs]
    part_files = [solution.part_file for solution in solutions]

    println("benchmark=$benchmark UB=$ub")
    println("将以下三个模型的 guided-best solution 用于 Cut-Overlay:")
    for (index, solution) in enumerate(solutions)
        println(
            "  [$index] cut=$(solution.guided_cut) seed=$(solution.seed) " *
            "part=$(solution.part_file)"
        )
    end

    out_dir = make_safe_output_dir(requested_out_dir)
    parts_out = joinpath(out_dir, "parts")
    mkpath(parts_out)
    mkpath(joinpath(out_dir, "logs"))

    ub2 = lpad(string(ub), 2, '0')
    final_part = joinpath(parts_out, "cutoverlay_three_models_ub$(ub2).part.2")
    seeds = make_seed_list(base_seed, num_seeds)

    start_time = time()
    cut, best_seed, overlay_build_elapsed, best_seed_elapsed =
        run_cutoverlay(hgr_file, part_files, ub, seeds, out_dir, final_part)
    total_elapsed = round(time() - start_time, digits=3)
    seed_detail_csv = joinpath(out_dir, "cutoverlay_final_seed_details.csv")
    seed_stats = calculate_final_seed_statistics(seed_detail_csv, ub)
    mean_final_cut = seed_stats.mean_final_cut

    sources_csv = joinpath(out_dir, "three_model_solution_sources.csv")
    open(sources_csv, "w") do io
        println(io, "model_index,ub,guided_cut,guided_seed,experiment_dir,part_file")
        for (index, solution) in enumerate(solutions)
            println(
                io,
                "$(index),$(ub),$(solution.guided_cut),$(solution.seed)," *
                "$(solution.exp_dir),$(solution.part_file)"
            )
        end
    end

    summary_csv = joinpath(out_dir, "cutoverlay_three_models_summary.csv")
    open(summary_csv, "w") do io
        println(
            io,
            "benchmark,ub,cutoverlay_cutsize,best_seed,cutoverlay_mean_cutsize," *
            "valid_seed_count,total_seed_count,total_elapsed_sec," *
            "overlay_build_elapsed_sec,best_seed_elapsed_sec,final_part"
        )
        println(
            io,
            "$(benchmark),$(ub),$(cut),$(best_seed),$(mean_final_cut)," *
            "$(seed_stats.valid_seed_count),$(seed_stats.total_seed_count),$(total_elapsed)," *
            "$(overlay_build_elapsed),$(best_seed_elapsed),$(final_part)"
        )
    end

    println("三个模型 solution 的 Cut-Overlay 完成")
    println("  cut=$cut")
    println(
        "  mean_final_cut=$(mean_final_cut) " *
        "(valid_seeds=$(seed_stats.valid_seed_count)/$(seed_stats.total_seed_count))"
    )
    println("  final_part=$final_part")
    println("  seed_details_csv=$seed_detail_csv")
    println("  sources_csv=$sources_csv")
    println("  summary_csv=$summary_csv")
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
