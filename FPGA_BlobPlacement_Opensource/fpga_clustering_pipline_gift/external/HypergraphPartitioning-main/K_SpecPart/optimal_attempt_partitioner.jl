function write_hypergraph(hgraph::__hypergraph__, fname::String)
    n = hgraph.num_vertices
    e = hgraph.num_hyperedges
    hedges = hgraph.eind
    eptr = hgraph.eptr
    hwts = hgraph.hwts
    vwts = hgraph.vwts
    fixed = hgraph.fixed
    wt_flag = maximum(vwts) > 1 ? true : false
    f = open(fname, "w")
    println(f, e, " ", n, " 11")

    for i in 1:e
        start_idx = eptr[i]
        end_idx = eptr[i+1]-1
        print(f, hwts[i])
        for j in start_idx:end_idx
            print(f, " ", hedges[j])
        end
        print(f, "\n")
    end
    for i in 1:n
        if wt_flag == 0
            println(f, vwts[i])
        else
            println(f, vwts[i]+1)
        end
    end

    close(f)

    if maximum(fixed) > -1
        f = open(fname*".fixed", "w")
        for i in 1:n
            println(f, fixed_vtxs[i])
        end
        close(f)
    end
end

function check_balance(hgraph::__hypergraph__, partition::Vector{Int}, num_parts::Int, ub_factor::Int)
    blocks = zeros(Int, num_parts)
    for i in 1:length(partition)
        blocks[partition[i]+1] += hgraph.vwts[i]
    end

    max_balance = Int(ceil((50 + ub_factor) * sum(hgraph.vwts)/100))
    for i in 1:num_parts
        if blocks[i] > max_balance
            return false
        end
    end
    return true
end

const ILP_TIMEOUT_SEC = 600   # kill ilp_part if it exceeds this

function _run_with_timeout(cmd::Cmd, timeout::Int)
    proc = run(cmd, wait=false)
    t0 = time()
    while process_running(proc)
        if time() - t0 > timeout
            kill(proc)
            @warn "ilp_part killed after $(timeout)s timeout"
            wait(proc)
            error("ilp_part timed out")
        end
        sleep(0.5)
    end
    success(proc) || throw(ProcessFailedException(proc))
end

function optimal_partitioner(hmetis_path::String, cplex_path::String, hgraph::__hypergraph__, num_parts::Int, ub_factor::Int; seed::Int=0)
    partition = zeros(Int, hgraph.num_vertices)
    hgr_file_name = tempname() * ".coarse.hgr"
    write_hypergraph(hgraph, hgr_file_name)

    # CPLEX community edition has unpredictable size limits (variables + constraints).
    # Even small problems crash with SIGABRT when num_parts > 2.
    # Disable ILP entirely and use hMETIS which is reliable.
    use_ilp = false

    if use_ilp
        ilp_ok = false
        try
            ilp_string = ilp_path * " " * hgr_file_name * " " * string(num_parts) * " " * string(ub_factor)
            ilp_command = `sh -c $ilp_string`
            _run_with_timeout(ilp_command, ILP_TIMEOUT_SEC)
            pfile = hgr_file_name * ".part." * string(num_parts)
            if isfile(pfile)
                f = open(pfile, "r")
                itr = 0
                for ln in eachline(f)
                    itr += 1
                    p = parse(Int, ln)
                    partition[itr] = p
                end
                close(f)
                (cutsize, ~) = golden_evaluator(hgraph, num_parts, partition)
                if check_balance(hgraph, partition, num_parts, ub_factor) && cutsize > 0
                    ilp_ok = true
                end
            end
        catch e
            @warn "ILP partitioner failed, falling back to hmetis: $e"
        end
        if !ilp_ok
            runs = 10; ctype = 1; rtype = 1; vcycle = 1; reconst = 0; dbglvl = 0
            hmetis_string = hmetis_path * " " * hgr_file_name * " " * string(num_parts) * " " * string(ub_factor) * " " * string(runs) * " " * string(ctype) * " " * string(rtype) * " " * string(vcycle) * " " * string(reconst) * " " * string(dbglvl) * " " * string(seed)
            hmetis_command = `sh -c $hmetis_string`
            run(hmetis_command, wait=true)
        end

        pfile = hgr_file_name * ".part." * string(num_parts)
        f = open(pfile, "r")
        itr = 0
        for ln in eachline(f)
            itr += 1
            p = parse(Int, ln)
            partition[itr] = p
        end
        close(f)

        try rm(hgr_file_name, force=true) catch end
        try rm(pfile, force=true) catch end
    else
        # Parallel hMETIS runs
        # Keep runs modest: 15 Julia sub-batches already run in parallel,
        # so spawning too many hMETIS processes causes CPU contention.
        parallel_runs = 3
        runs = 5; ctype = 1; rtype = 1; vcycle = 1; reconst = 0; dbglvl = 0
        partitions = [zeros(Int, length(partition)) for i in 1:parallel_runs]
        cutsizes = zeros(Int, parallel_runs)
        fail_count = 0
        @sync Threads.@threads for i in 1:parallel_runs
            local_hgr_name = hgr_file_name * "." * string(i)
            try
                cp(hgr_file_name, local_hgr_name, force=true)
                hmetis_string = hmetis_path * " " * local_hgr_name * " " * string(num_parts) * " " * string(ub_factor) * " " * string(runs) * " " * string(ctype) * " " * string(rtype) * " " * string(vcycle) * " " * string(reconst) * " " * string(dbglvl) * " " * string(seed + i)
                hmetis_command = `sh -c $hmetis_string`
                run(hmetis_command, wait=true)
            catch e
                @warn "[optimal_partitioner] hMETIS run $i failed: $e"
                fail_count += 1
            end
        end
        for i in 1:parallel_runs
            local_hgr_name = hgr_file_name * "." * string(i)
            local_pfile_name = local_hgr_name * ".part." * string(num_parts)
            try
                if isfile(local_pfile_name)
                    f = open(local_pfile_name, "r")
                    itr = 0
                    for ln in eachline(f)
                        itr += 1
                        p = parse(Int, ln)
                        partitions[i][itr] = p
                    end
                    close(f)
                    (cutsizes[i], ~) = golden_evaluator(hgraph, num_parts, partitions[i])
                else
                    cutsizes[i] = typemax(Int)
                end
            catch e
                cutsizes[i] = typemax(Int)
            end
            try rm(local_hgr_name, force=true) catch end
            try rm(local_pfile_name, force=true) catch end
        end
        ~, best_cut_idx = findmin(cutsizes)
        try rm(hgr_file_name, force=true) catch end
        partition = partitions[best_cut_idx]
    end
    return partition
end