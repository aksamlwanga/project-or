from flask import Flask, request, jsonify, render_template, redirect, url_for
import pulp
import json
import urllib.parse

app = Flask(__name__)

# Route for the main index page
@app.route('/')
def index():
    return render_template('index.html')

# Show Results
@app.route('/results', methods=['POST'])
def results():
    status = request.form.get('status')
    method = request.form.get('method')
    total_cost = request.form.get('total_cost')
    results = json.loads(request.form.get('results'))
    constraints_status = json.loads(request.form.get('constraints_status'))
    dummy_info = request.form.get('dummy_info')
    results=dict(sorted(results.items(), key=lambda item: item[1], reverse=True))
    
    return render_template('results.html', status=status, method=method, total_cost=total_cost, results=results, constraints_status=constraints_status, dummy_info=dummy_info)

# Route for solving the transportation/transshipment problem
@app.route('/solve', methods=['POST'])
def solve():
    data = request.get_json()

    # Received data for debugging
    # print("Received data:", data)

    problem_type = data['problem_type']
    supply = data['supply']
    cc_demand = data['demand']
    demand = {key.replace("Los Canos", "LosCanos"): value for key, value in cc_demand.items()}
    
    if problem_type == 'transportation':
        cc_plant_to_site_costs = data['plant_to_site_costs']
        plant_to_site_costs = {key.replace("Los Canos", "LosCanos"): value for key, value in cc_plant_to_site_costs.items()}
        # Convert keys to tuples and values to integers
        costs = {tuple(map(str.strip, k.strip('()').split(','))): int(v) for k, v in plant_to_site_costs.items()}
        
        total_supply = sum(supply.values())
        total_demand = sum(demand.values())
        dummy_info = []

        # Add dummy demand if total supply exceeds total demand
        if total_supply > total_demand:
            dummy_demand = total_supply - total_demand
            demand['Dummy'] = dummy_demand
            for i in supply.keys():
                costs[(i, 'Dummy')] = 0
            dummy_info.append(f"Added dummy demand of {dummy_demand} units.")
        # Add dummy supply if total demand exceeds total supply
        elif total_demand > total_supply:
            dummy_supply = total_demand - total_supply
            supply['Dummy'] = dummy_supply
            for j in demand.keys():
                costs[('Dummy', j)] = 0
            dummy_info.append(f"Added dummy supply of {dummy_supply} units.")
            
        # Call the solve_transportation function
        status, method, total_cost, mapped_results, constraints_status = solve_transportation(costs, supply, demand)
        
        # Redirect to the results page with parameters
        return jsonify({
            'redirect_url': url_for('results'), 
            'status': status,
            'method': method,
            'total_cost': total_cost,
            'results': mapped_results,
            'constraints_status': constraints_status,
            'dummy_info': dummy_info
        })
    
    elif problem_type == 'transshipment':
        cc_transshipment_costs = data['transshipment_costs']
        transshipment_costs = {key.replace("Los Canos", "LosCanos"): value for key, value in cc_transshipment_costs.items()}
        # Convert keys to tuples and values to integers
        transshipment_costs = {tuple(map(str.strip, k.strip('()').split(','))): int(v) for k, v in transshipment_costs.items() if v is not None}
        cc_plant_to_site_costs = data['plant_to_site_costs']
        plant_to_site_costs = {key.replace("Los Canos", "LosCanos"): value for key, value in cc_plant_to_site_costs.items()}
        plant_to_site_costs = {tuple(map(str.strip, k.strip('()').split(','))): int(v) for k, v in plant_to_site_costs.items() if v is not None}

        total_supply = sum(supply.values())
        total_demand = sum(demand.values())
        dummy_info = []

        # Add dummy demand if total supply exceeds total demand
        if total_supply > total_demand:
            dummy_demand = total_supply - total_demand
            demand['Dummy'] = dummy_demand
            for i in supply.keys():
                for intermediate_node in supply.keys():  # intermediate nodes are the same as supply nodes
                    transshipment_costs[(i, intermediate_node)] = transshipment_costs.get((i, intermediate_node), 0)
                plant_to_site_costs[(i, 'Dummy')] = 0
            dummy_info.append(f"Added dummy demand of {dummy_demand} units.")
             
        # Add dummy supply if total demand exceeds total supply
        elif total_demand > total_supply:
            dummy_supply = total_demand - total_supply
            supply['Dummy'] = dummy_supply
            for intermediate_node in supply.keys():
                transshipment_costs[('Dummy', intermediate_node)] = 0
            dummy_info.append(f"Added dummy supply of {dummy_supply} units.")

        # Ensure there's no ('Dummy', 'Dummy') in transshipment_costs
        if ('Dummy', 'Dummy') in transshipment_costs:
            del transshipment_costs[('Dummy', 'Dummy')]

        # Call the solve_transshipment function
        status, method, total_cost, mapped_results, constraints_status = solve_transshipment(supply, demand,transshipment_costs,plant_to_site_costs)

        # Redirect to the results page with parameters
        return jsonify({
            'redirect_url': url_for('results'), 
            'status': status,
            'method': method,
            'total_cost': total_cost,
            'results': mapped_results,
            'constraints_status': constraints_status,
            'dummy_info': dummy_info
        })

# Function to solve the transportation problem
def solve_transportation(costs, supply, demand):
    print("Costs:", costs)
    print("Supply:", supply)
    print("Demand:", demand)
   
    # Create a linear programming problem
    prob = pulp.LpProblem("Transportation_Problem", pulp.LpMinimize)

    # Create decision variables for each route
    routes = [(i, j) for i in supply.keys() for j in demand.keys()]
    route_vars = pulp.LpVariable.dicts("Route", (supply.keys(), demand.keys()), lowBound=0, cat='Integer')

    # Objective function: Minimize the total transportation cost
    prob += pulp.lpSum([route_vars[i][j] * costs.get((i, j), 0) for (i, j) in routes]), "Total_Transportation_Cost"

    # Supply constraints: The sum of shipments from each supply point should equal the supply
    for i in supply.keys():
        prob += pulp.lpSum([route_vars[i][j] for j in demand.keys()]) == supply[i], f"Supply_{i}"

    # Demand constraints: The sum of shipments to each demand point should equal the demand
    for j in demand.keys():
        prob += pulp.lpSum([route_vars[i][j] for i in supply.keys()]) == demand[j], f"Demand_{j}"

    # Solve the problem
    prob.solve()

    # Retrieve the results
    results = {(i, j): route_vars[i][j].varValue for (i, j) in routes}
    total_cost = pulp.value(prob.objective)
    status = pulp.LpStatus[prob.status]
    method = "Transportation Approach"

    # Define plant and demand names
    plant_names = list(supply.keys())
    demand_names = list(demand.keys())

    # Map the results for better readability
    mapped_results = {}
    for (i, j) in routes:
        from_name = plant_names[plant_names.index(i)]
        to_name = demand_names[demand_names.index(j)]
        value = results.get((i, j), 0)
        mapped_results[f"Route from {from_name} to {to_name}"] = value

    # Capture the constraints status (shadow price and slack)
    constraints_status = {
        f"Supply_{i}": (pulp.value(prob.constraints[f"Supply_{i}"].pi), pulp.value(prob.constraints[f"Supply_{i}"].slack))
        for i in supply.keys()
    }
    constraints_status.update({
        f"Demand_{j}": (pulp.value(prob.constraints[f"Demand_{j}"].pi), pulp.value(prob.constraints[f"Demand_{j}"].slack))
        for j in demand.keys()
    })

    # Return the results
    return status, method, total_cost, mapped_results, constraints_status


# # Function to solve the transshipment problem

def solve_transshipment(supply, demand, transshipment_costs, destination_costs):
         # Define the sets of nodes from each dictionary
         supply_nodes = set(supply.keys())
         transshipment_nodes = set(x[0] for x in transshipment_costs.keys()).union(x[1] for x in transshipment_costs.keys())
         demand_nodes = set(demand.keys())
         destination_nodes = set(x[0] for x in destination_costs.keys())
         
         key_to_remove = 'Dummy'
        #  # Check if the key exists in the transshipment_nodes set and remove it if it does
         if key_to_remove in transshipment_nodes:
             transshipment_nodes.remove(key_to_remove)
             print(f"Key '{key_to_remove}' was removed from transshipment_nodes."), 
         else:
           print(f"Key '{key_to_remove}' does not exist in transshipment_nodes.")    
         
         transshipment_problem = pulp.LpProblem("Transshipment_Problem", pulp.LpMinimize)
         
         # Define decision variables: Quantities of goods transported between nodes
         # x_ij where i is the source node and j is the destination node (including transshipment nodes)
         x = {}
         # Variables for shipments between supply/transshipment nodes
         for i in supply_nodes.union(transshipment_nodes):  # Include Dummy as a supply node if needed
            for j in transshipment_nodes:
                # if i != j:  # Avoid self-loop
                    x[(i, j)] = pulp.LpVariable(f"x_{i}_to_{j}", lowBound=0, cat='Integer')
        # Variables for shipments from transshipment nodes to demand nodes
         for i in transshipment_nodes: 
            for j in demand_nodes:
                x[(i, j)] = pulp.LpVariable(f"x_{i}_to_{j}", lowBound=0, cat='Integer')
        
         total_cost = pulp.lpSum(x[(i, j)] * transshipment_costs.get((i, j), 0) for i, j in x.keys() if (i, j) in transshipment_costs) \
           + pulp.lpSum(x[(i, j)] * destination_costs.get((i, j), 0) for i, j in x.keys() if (i, j) in destination_costs)
         
         transshipment_problem += total_cost, "Total Transportation Cost"
         
         # # Supply constraints for each supply node
         for s in supply.keys():
           transshipment_problem += (pulp.lpSum(x[(s, d)] for d in transshipment_nodes if (s, d) in x) == supply[s], f"Supply_Limit_{s}")

         # Demand constraints for each demand node
         for d in demand.keys():
           transshipment_problem += (pulp.lpSum(x[(s, d)] for s in transshipment_nodes if (s, d) in x) == demand[d], f"Demand_Requirement_{d}")

         # Balance constraints for each transshipment node
         for t in transshipment_nodes:
            # Calculate the total inflow to transshipment node 't' from all other nodes
           total_inflow = pulp.lpSum(x[(s, t)] for s in supply_nodes.union(transshipment_nodes) if (s, t) in x)
    
            # Calculate the total outflow from transshipment node 't' to only the demand nodes, not other transshipment nodes
           total_outflow = pulp.lpSum(x[(t, d)] for d in demand_nodes if (t, d) in x)

           transshipment_problem += (total_inflow == total_outflow, f"Flow_Balance_{t}")
 
         print("Constraints Defined:", transshipment_problem.constraints)

        #Solve the problem
         transshipment_problem.solve()
         # Retrieve the results
         results = {(i, j): x[(i, j)].varValue for (i, j) in x  }
         mapped_results = {f"Route from {i} to {j}": value for (i, j), value in results.items()}

         # Constraint statuses (shadow prices and slack)
         constraints_status = {name: (pulp.value(transshipment_problem.constraints[name].pi), pulp.value(transshipment_problem.constraints[name].slack)) for name in transshipment_problem.constraints}

         return pulp.LpStatus[transshipment_problem.status], "Transshipment Approach", pulp.value(transshipment_problem.objective), mapped_results, constraints_status
  
if __name__ == '__main__':
    app.run(debug=True)
