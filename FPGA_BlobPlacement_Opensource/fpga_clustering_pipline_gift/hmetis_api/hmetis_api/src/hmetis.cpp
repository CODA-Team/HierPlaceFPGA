// If there is no valid result, the output will be empty file
#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <sstream>
#include <algorithm>
#include <fstream>
#include <iterator>
#include <cmath>
#include <chrono>
#include <iomanip>

// Using hMetis library
extern "C" {
  void HMETIS_PartRecursive (int nvtxs, int nhedges, int *vwgts,
                             int *eptr, int *eind, int *hewgts,
                             int nparts, int ubfactor,
                             int *options, int *part, int *edgecut);
};


int main(int argc, char* argv[]) {
  std::string hypergraph_file = "";
  std::string fixed_file = "";
  int Nparts = 2;
  int UBfactor = 5;
  int Nruns = 10;
  int CType = 1;
  int RType = 1;
  int Vcycle = 1;
  int Reconst = 0;
  int dbglvl = 16;
  int seed = 0;

  if(argc == 4) {
    hypergraph_file = std::string(argv[1]);
    Nparts = std::stoi(std::string(argv[2]));
    UBfactor = std::stoi(std::string(argv[3]));
  } else if(argc == 5) {
    hypergraph_file = std::string(argv[1]);
    fixed_file = std::string(argv[2]);
    Nparts = std::stoi(std::string(argv[3]));
    UBfactor = std::stoi(std::string(argv[4]));
  } else if(argc == 10) {
    hypergraph_file = std::string(argv[1]);
    Nparts = std::stoi(std::string(argv[2]));
    UBfactor = std::stoi(std::string(argv[3]));
    Nruns = std::stoi(std::string(argv[4]));
    CType = std::stoi(std::string(argv[5]));
    RType = std::stoi(std::string(argv[6]));
    Vcycle = std::stoi(std::string(argv[7]));
    Reconst = std::stoi(std::string(argv[8]));
    dbglvl = std::stoi(std::string(argv[9]));
   } else if(argc == 11) {
    hypergraph_file = std::string(argv[1]);
    Nparts = std::stoi(std::string(argv[2]));
    UBfactor = std::stoi(std::string(argv[3]));
    Nruns = std::stoi(std::string(argv[4]));
    CType = std::stoi(std::string(argv[5]));
    RType = std::stoi(std::string(argv[6]));
    Vcycle = std::stoi(std::string(argv[7]));
    Reconst = std::stoi(std::string(argv[8]));
    dbglvl = std::stoi(std::string(argv[9]));
    seed = std::stoi(std::string(argv[10]));
  } else if(argc == 12) {
    hypergraph_file = std::string(argv[1]);
    fixed_file = std::string(argv[2]);
    Nparts = std::stoi(std::string(argv[3]));
    UBfactor = std::stoi(std::string(argv[4]));
    Nruns = std::stoi(std::string(argv[5]));
    CType = std::stoi(std::string(argv[6]));
    RType = std::stoi(std::string(argv[7]));
    Vcycle = std::stoi(std::string(argv[8]));
    Reconst = std::stoi(std::string(argv[9]));
    dbglvl = std::stoi(std::string(argv[10]));
    seed = std::stoi(std::string(argv[11]));
  } else {
    std::cout << std::string(80, '*') << std::endl;
    std::cout << "Usage of hMetis:  " << std::endl;
    std::cout << "[Option1]:  hmetis HGraphFile Nparts UBfactor" << std::endl;
    std::cout << "[Option2]:  hmetis HGraphFile FixFile Nparts UBfactor" << std::endl;
    std::cout << "[Option3]:  hmetis HGraphFile Nparts UBfactor Nruns ";
    std::cout << "CType RType Vcycle Reconst dbglvl" << std::endl;
    std::cout << "[Option4]:  hmetis HGraphFile FixFile Nparts UBfactor Nruns ";
    std::cout << "CType RType Vcycle Reconst dbglvl" << std::endl;
  }

  // print options
  std::cout << "[INFO] HGraphFile : " << hypergraph_file << std::endl;
  std::cout << "[INFO] FixFile : " << fixed_file << std::endl;
  std::cout << "[INFO] Nparts : " << Nparts << std::endl;
  std::cout << "[INFO] UBfactor : " << UBfactor << std::endl;
  std::cout << "[INFO] Nruns : " << Nruns << std::endl;
  std::cout << "[INFO] CType : " << CType << std::endl;
  std::cout << "[INFO] RType : " << RType << std::endl;
  std::cout << "[INFO] Vcycle : " << Vcycle << std::endl;
  std::cout << "[INFO] Reconst : " << Reconst << std::endl;
  std::cout << "[INFO] dbglvl : " << dbglvl << std::endl;
  std::cout << "[INFO] seed : "   << seed << std::endl;




  std::string solution_file = hypergraph_file + std::string(".part.") + std::to_string(Nparts);
  
  auto start_timestamp = std::chrono::high_resolution_clock::now();


  // *******************************************
  // Read hypergraph and fixed vertices
  // ******************************************
  int edgecut = -1;
  int num_vertices = 4;
  int num_hyperedges = 7;
  int flag = 0;
  
  std::vector<int> vertices_weight;
  std::vector<int> hyperedges_weight;
  std::vector<int> hyperedges_ind;
  std::vector<int> hyperedges_ptr;
  std::vector<int> vertices_part;

  std::ifstream hypergraph_file_input(hypergraph_file);
  if(!hypergraph_file_input.is_open()) {                                 
    std::cout << "Can not open " << hypergraph_file << std::endl;        
    std::ofstream solution_file_output;
    solution_file_output.open(solution_file);
    solution_file_output.close();
    return 1;                                                                           
  }   

  std::string cur_line;
  std::getline(hypergraph_file_input, cur_line);
  std::istringstream cur_line_buf(cur_line);
  std::vector<int> stats {std::istream_iterator<int>(cur_line_buf), std::istream_iterator<int>()};
  num_hyperedges = stats[0];
  num_vertices = stats[1];
  if(stats.size() == 3) {
    flag = stats[2];
  }

  for(int i = 0; i < num_hyperedges; i++) {
    std::getline(hypergraph_file_input, cur_line);
    std::istringstream cur_line_buf(cur_line);
    std::vector<int> net { std::istream_iterator<int>(cur_line_buf),                                
                           std::istream_iterator<int>() };
    hyperedges_ptr.push_back(hyperedges_ind.size());
    if((flag % 10) == 1) {
      hyperedges_weight.push_back(net[0]);
      for(int j = 1; j < net.size(); j++) 
        hyperedges_ind.push_back(net[j] - 1);
    } else {
      for(auto& vertex : net)
        hyperedges_ind.push_back(vertex - 1);
    }
  }

  hyperedges_ptr.push_back(hyperedges_ind.size());
  
  if(flag >= 10) {
    for(int i = 0; i < num_vertices; i++) {
      std::getline(hypergraph_file_input, cur_line);
      vertices_weight.push_back(std::stoi(cur_line));
    }  
  }

  hypergraph_file_input.close();

  if(fixed_file.size() != 0) {
    std::ifstream fixed_file_input(fixed_file);
    if(!fixed_file_input.is_open()) {                                 
      std::cout << "Can not open " << fixed_file << std::endl;        
      std::ofstream solution_file_output;
      solution_file_output.open(solution_file);
      solution_file_output.close();
      return 1;                                                                           
    }
    
    int part_id = -1;
    while(fixed_file_input >> part_id)
      vertices_part.push_back(part_id);
    
    fixed_file_input.close();
  }


  int* vwgts = nullptr;
  if(vertices_weight.size() > 0) {
    vwgts = (int*) malloc((unsigned) num_vertices * sizeof(int));
    for(int i = 0; i < vertices_weight.size(); i++)
      vwgts[i] = vertices_weight[i];
  }

  
  int* hewgts = nullptr;
  if(hyperedges_weight.size() > 0) {
    hewgts = (int*) malloc((unsigned) num_hyperedges * sizeof(int));
    for(int i = 0; i < hyperedges_weight.size(); i++)
      hewgts[i] = hyperedges_weight[i];
  }

  int* eind = (int*) malloc((unsigned) hyperedges_ind.size() * sizeof(int));
  for(int i = 0; i < hyperedges_ind.size(); i++)
    eind[i] = hyperedges_ind[i];

  int* eptr = (int*) malloc((unsigned) hyperedges_ptr.size() * sizeof(int));
  for(int i = 0; i < hyperedges_ptr.size(); i++)
    eptr[i] = hyperedges_ptr[i];

  int* part = (int*) malloc((unsigned) num_vertices * sizeof(int));
  if(vertices_part.size() == num_vertices) {
    for(int i = 0; i < num_vertices; i++)
      part[i] = vertices_part[i];
  }


  int options[9] = { 0 };
  options[0] = 1;
  options[1] = Nruns;
  options[2] = CType;
  options[3] = RType;
  options[4] = Vcycle;
  options[5] = Reconst;
  options[6] = 0;
  if(vertices_part.size() == num_vertices)
    options[7] = 1;

  options[7] = seed;
  options[8] = dbglvl;

    
  // ******************************************************************
  // Call hMetis
  // ******************************************************************
  HMETIS_PartRecursive (num_vertices, num_hyperedges, vwgts,
                        eptr, eind, hewgts, Nparts, UBfactor,
                        options, part, &edgecut);
  
  std::cout << "[INFO] Final CutSize : " << edgecut << std::endl;
  
  float total_weight = 0.0;
  std::vector<float> blocks_balance(Nparts, 0.0);
  for (int i = 0; i < num_vertices; i++) {
    float weight = (vertices_weight.size() == 0) ? 1.0 : vertices_weight[i];
    total_weight += weight;
    blocks_balance[part[i]] += weight;
  }
  
  float max_balance = (100.0 / Nparts  + UBfactor) * 0.01;
  max_balance *= total_weight;
  
  for (auto& balance : blocks_balance) {
    balance = balance / total_weight;
    if (balance > max_balance) {
      std::ofstream solution_file_output;
      solution_file_output.open(solution_file);
      solution_file_output.close();
      return 1;
    }
  }

  std::cout << "[INFO] Final Balance :  ";
  for (auto& balance : blocks_balance)
    std::cout <<  std::fixed << std::setprecision(5) <<  balance  << "   ";
  std::cout << std::endl;
  
  std::ofstream solution_file_output;
  solution_file_output.open(solution_file);
  for (int i = 0; i < num_vertices; i++)
    solution_file_output << part[i] << std::endl;
  
  solution_file_output.close();
  
  auto end_timestamp = std::chrono::high_resolution_clock::now();
  double time_taken = std::chrono::duration_cast<std::chrono::nanoseconds>(end_timestamp - start_timestamp).count();
  time_taken *= 1e-9;
  std::cout << "[INFO] Runtime:  " << std::fixed << std::setprecision(2) << time_taken << " sec" << std::endl;
  return 0;
}













