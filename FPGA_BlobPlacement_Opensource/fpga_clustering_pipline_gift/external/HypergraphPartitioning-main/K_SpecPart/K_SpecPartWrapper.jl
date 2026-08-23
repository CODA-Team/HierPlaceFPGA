#!/usr/bin/env julia
#
# K_SpecPartWrapper.jl — CLI wrapper around K_SpecPart for direct K-way partitioning.
#
# Supports single mode (--hgr / --output / --num_parts) and batch mode (--batch manifest.json).
# Overrides triton_part_refine as a no-op since OpenROAD is not available.
#

using JSON
using LinearAlgebra
using DelimitedFiles

# ---------- Load SpecPart module ----------
const WRAPPER_DIR = @__DIR__
include(joinpath(WRAPPER_DIR, "specpart.jl"))

# ---------- Override triton_part_refine as no-op ----------
function SpecPart.triton_part_refine(
    refiner_path::String, hypergraph::String, partition::String,
    num_parts::Int, ub_factor::Int, seed::Int, id::Int
)
    @info "[K_SpecPartWrapper] triton_part_refine skipped (no-op)"
    return nothing
end

# ---------- Generate initial hint via hmetis ----------
function generate_hmetis_hint(hgr_file::String, num_parts::Int, ub_factor::Int, n::Int; seed::Int=0)
    hint_partition = zeros(Int, n)
    hint_file = hgr_file * ".hint.part." * string(num_parts)
    try
        runs = 10; ctype = 1; rtype = 1; vcycle = 1; reconst = 0; dbglvl = 0
        hmetis_cmd = SpecPart.hmetis_path * " " * hgr_file * " " *
            string(num_parts) * " " * string(ub_factor) * " " *
            string(runs) * " " * string(ctype) * " " * string(rtype) * " " *
            string(vcycle) * " " * string(reconst) * " " * string(dbglvl) * " " *
            string(seed)
        run(`sh -c $hmetis_cmd`, wait=true)
        # hmetis writes to <hgr_file>.part.<K>
        hmetis_out = hgr_file * ".part." * string(num_parts)
        if isfile(hmetis_out)
            hint_partition = SpecPart.read_hint_file(hmetis_out)
            cp(hmetis_out, hint_file, force=true)
            rm(hmetis_out, force=true)
            @info "[K_SpecPartWrapper] hmetis hint generated ($(length(hint_partition)) vertices)"
            return hint_file, hint_partition
        end
    catch e
        @warn "[K_SpecPartWrapper] hmetis hint generation failed: $e"
    end
    # Fallback: write all-zeros hint
    open(hint_file, "w") do f
        for i in 1:n
            println(f, 0)
        end
    end
    return hint_file, hint_partition
end

# ---------- Write clusters JSON result ----------
function write_result(output_file::String, partition::Vector{Int}, n::Int, num_parts_actual::Int)
    # partition is 0-based partition IDs for vertices 1..n
    actual_K = max(1, maximum(partition) + 1)
    clusters = [Int[] for _ in 1:actual_K]
    for i in 1:n
        pid = partition[i] + 1  # 0-based → 1-based partition index
        pid = clamp(pid, 1, actual_K)
        push!(clusters[pid], i)  # 1-based vertex ID
    end
    # Remove empty clusters
    clusters = filter(!isempty, clusters)
    if isempty(clusters)
        clusters = [collect(1:n)]
    end
    # Build cluster_map (0-based partition IDs, indexed by 1-based vertex ID)
    cluster_map = zeros(Int, n)
    for (cid, cl) in enumerate(clusters)
        for v in cl
            cluster_map[v] = cid - 1
        end
    end
    result = Dict(
        "clusters"    => clusters,
        "cluster_map" => collect(cluster_map),
        "stats"       => Dict("num_clusters" => length(clusters))
    )
    open(output_file, "w") do f
        JSON.print(f, result)
    end
end

# ---------- Run a single K_SpecPart job ----------
function run_single_job(hgr_file::String, output_file::String, num_parts::Int;
                        imb::Int=2, eigvecs::Int=2, refine_iters::Int=2,
                        solver_iters::Int=40, best_solns::Int=3, seed::Int=0,
                        features_file::String="", specpart_mode::String="gift_single")
    @info "[K_SpecPartWrapper] Processing $hgr_file  K=$num_parts  features=$(features_file == "" ? "none" : features_file)  mode=$specpart_mode"

    # 1. Read hypergraph
    hypergraph = SpecPart.read_hypergraph_file(hgr_file)
    n = hypergraph.num_vertices
    if n <= 1 || hypergraph.num_hyperedges == 0
        write_result(output_file, zeros(Int, n), n, 1)
        return
    end
    if num_parts >= n
        # More parts than vertices — just assign each vertex its own cluster
        write_result(output_file, collect(0:n-1), n, n)
        return
    end

    # 2. Isolate islands to get mapping (we need original_indices later)
    (processed_hg, original_indices, new_indices, unused_indices) =
        SpecPart.isolate_islands(hypergraph)

    # 3. Generate initial hmetis hint
    hint_file, hint_partition = generate_hmetis_hint(hgr_file, num_parts, imb, n; seed=seed)

    # 4. Call specpart_run (with fallback to hmetis hint on failure)
    output_partition = zeros(Int, n)
    cutsize = 0
    specpart_ok = false
    use_features = features_file != "" && isfile(features_file)
    try
        if use_features
            features = readdlm(features_file, Float64)
            @info "[K_SpecPartWrapper] Using GIFT features: $(size(features))"
            refined_partition, cutsize = SpecPart.specpart_run_with_features(
                hgr_file,
                features,
                hint_file    = hint_file,
                imb          = imb,
                num_parts    = num_parts,
                refine_iters = refine_iters,
                best_solns   = best_solns,
                seed         = seed,
                specpart_mode = specpart_mode,
            )
        else
            refined_partition, cutsize = SpecPart.specpart_run(
                hgr_file,
                hint_file    = hint_file,
                imb          = imb,
                num_parts    = num_parts,
                eigvecs      = eigvecs,
                refine_iters = refine_iters,
                solver_iters = solver_iters,
                best_solns   = best_solns,
                seed         = seed,
            )
        end
        # 5. Map back to original vertex indices
        for new_i in 1:length(original_indices)
            orig_i = original_indices[new_i]
            if new_i <= length(refined_partition)
                output_partition[orig_i] = refined_partition[new_i]
            end
        end
        specpart_ok = true
    catch e
        @error "[K_SpecPartWrapper] specpart_run EXCEPTION: $(sprint(showerror, e))"
        @warn "[K_SpecPartWrapper] specpart_run failed, using hmetis hint" exception=(e, catch_backtrace())
        if length(hint_partition) == n
            output_partition = hint_partition
        end
    end

    # 6. Clean up hint file
    try rm(hint_file, force=true) catch end

    # 7. Clean up any leftover temp files from specpart
    for pat in ["*.processed", "*.specpart.*"]
        try run(`sh -c $("""rm -f $(hgr_file).$pat 2>/dev/null""")`, wait=true) catch end
    end

    # 8. Write result
    write_result(output_file, output_partition, n, num_parts)
    status = specpart_ok ? "specpart" : "hmetis-fallback"
    @info "[K_SpecPartWrapper] Done ($status): cutsize=$cutsize  partitions=$(maximum(output_partition)+1)"
end

# ---------- CLI ----------
function main()
    args = ARGS

    if "--batch" in args
        # ---- Batch mode ----
        batch_idx = findfirst(x -> x == "--batch", args)
        manifest_path = args[batch_idx + 1]
        manifest = JSON.parsefile(manifest_path)
        jobs = manifest["jobs"]
        per_job_timeout = get(manifest, "per_job_timeout", 120)  # seconds per job
        @info "[K_SpecPartWrapper] Batch mode: $(length(jobs)) jobs, per_job_timeout=$(per_job_timeout)s"

        n_ok = 0; n_timeout = 0; n_fail = 0
        batch_t0 = time()

        for (i, job) in enumerate(jobs)
            hgr_path      = job["hgr_path"]
            output_path   = job["output_path"]
            num_parts     = get(job, "num_parts", 2)
            seed          = get(job, "seed", 0)
            imb           = get(job, "imb", get(job, "ub", 2))
            eigvecs       = get(job, "eigvecs", 2)
            refine_iters  = get(job, "refine_iters", 2)
            solver_iters  = get(job, "solver_iters", 40)
            best_solns    = get(job, "best_solns", 3)
            feat_file     = get(job, "features_file", "")
            sp_mode       = get(job, "specpart_mode", "gift_single")

            @info "[K_SpecPartWrapper] Job $i/$(length(jobs)): K=$num_parts  mode=$sp_mode  $(basename(hgr_path))"
            job_t0 = time()
            try
                run_single_job(hgr_path, output_path, num_parts;
                               imb=imb, eigvecs=eigvecs, refine_iters=refine_iters,
                               solver_iters=solver_iters, best_solns=best_solns, seed=seed,
                               features_file=feat_file, specpart_mode=sp_mode)
                elapsed = time() - job_t0
                @info "[K_SpecPartWrapper] Job $i completed in $(round(elapsed, digits=1))s"
                n_ok += 1
            catch e
                elapsed = time() - job_t0
                @error "[K_SpecPartWrapper] Job $i FAILED after $(round(elapsed, digits=1))s" exception=(e, catch_backtrace())
                n_fail += 1
                # Write fallback single-cluster result
                if !isfile(output_path)
                    try
                        hg = SpecPart.read_hypergraph_file(hgr_path)
                        write_result(output_path, zeros(Int, hg.num_vertices), hg.num_vertices, 1)
                    catch e2
                        @error "[K_SpecPartWrapper] Fallback also failed: $e2"
                    end
                end
            end
        end

        batch_elapsed = time() - batch_t0
        @info "[K_SpecPartWrapper] Batch done in $(round(batch_elapsed, digits=1))s: $n_ok ok, $n_fail failed ($(length(jobs)) total)"
    else
        # ---- Single mode ----
        hgr_file = ""; output_file = ""; num_parts = 2; imb = 2
        eigvecs = 2; refine_iters = 2; solver_iters = 40; best_solns = 3; seed = 0

        i = 1
        while i <= length(args)
            a = args[i]
            if     a == "--hgr"           ; hgr_file      = args[i+1]; i += 2
            elseif a == "--output"        ; output_file   = args[i+1]; i += 2
            elseif a == "--num_parts"     ; num_parts     = parse(Int, args[i+1]); i += 2
            elseif a == "--imb"           ; imb           = parse(Int, args[i+1]); i += 2
            elseif a == "--eigvecs"       ; eigvecs       = parse(Int, args[i+1]); i += 2
            elseif a == "--refine_iters"  ; refine_iters  = parse(Int, args[i+1]); i += 2
            elseif a == "--solver_iters"  ; solver_iters  = parse(Int, args[i+1]); i += 2
            elseif a == "--best_solns"    ; best_solns    = parse(Int, args[i+1]); i += 2
            elseif a == "--seed"          ; seed          = parse(Int, args[i+1]); i += 2
            else   i += 1
            end
        end

        if hgr_file == "" || output_file == ""
            @error "Usage: julia K_SpecPartWrapper.jl --hgr <file> --output <file> --num_parts <K> [options]"
            exit(1)
        end

        run_single_job(hgr_file, output_file, num_parts;
                       imb=imb, eigvecs=eigvecs, refine_iters=refine_iters,
                       solver_iters=solver_iters, best_solns=best_solns, seed=seed)
    end
end

main()
