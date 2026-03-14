/**
 * Fetches graph data from the Flask backend API
 * @returns {Object} Graph data containing nodes and edges
 */
console.log("✅ script.js foi carregado com sucesso!");
console.log("📊 D3 disponível?", typeof d3 !== 'undefined');
async function loadGraph() {
    console.log(window.GRAPH_DATA)
    return window.GRAPH_DATA
}


// Canvas dimensions
const width = 1600
const height = 1200

// Load graph data from API
var graph = await loadGraph()

// Transform nodes: add random initial positions
const nodes = graph.data.nodes.map(d => ({
    ...d,
    x: Math.random() * width,
    y: Math.random() * height
}))

const margin = 20;

// Transform edges: copy data as-is
const edges = graph.data.edges.map(d => ({...d}))

console.log("nodes:", nodes)
console.log("edges:", edges)

// ========== DEBUG - Procurando nó problemático ==========
console.log("\n🔍 DEBUG - Procurando nó problemático");
const problemId = '4:b1077f90-fe40-4c7e-8e8f-7fb1b02d1fa7:9';
const foundNode = nodes.find(n => n.id === problemId);

if (foundNode) {
    console.log("✅ Nó problemático ENCONTRADO:", foundNode);
} else {
    console.log("🔴 Nó problemático NÃO ENCONTRADO!");
    console.log("🔍 Primeiros 5 IDs dos nodes:");
    nodes.slice(0, 5).forEach(n => console.log(`   - ${n.id}`));
}

// Procurar edges que usam esse ID
const edgesWithProblem = edges.filter(e =>
    e.source === problemId || e.target === problemId
);
console.log("🔗 Edges com ID problemático:", edgesWithProblem.length);
edgesWithProblem.forEach(e => {
    console.log(`   Source: ${e.source}`);
    console.log(`   Target: ${e.target}`);
});

// Verificar se TODOS os edges têm nós correspondentes
const nodeIds = new Set(nodes.map(n => n.id));
const orphanEdges = edges.filter(e =>
    !nodeIds.has(e.source) || !nodeIds.has(e.target)
);

if (orphanEdges.length > 0) {
    console.log(`\n🔴 FRONTEND: Encontrados ${orphanEdges.length} edges órfãos!`);
    orphanEdges.slice(0, 3).forEach(e => {
        console.log(`   Source: ${e.source} (existe: ${nodeIds.has(e.source)})`);
        console.log(`   Target: ${e.target} (existe: ${nodeIds.has(e.target)})`);
    });
} else {
    console.log("\n✅ FRONTEND: Todos os edges têm nós correspondentes!");
}
console.log("===================\n");
// ========== FIM DO DEBUG ==========

// Initialize SVG canvas and disable text selection
const svg = d3.select("#graph")
    .style("user-select", "none")
    .style("-webkit-user-select", "none")
    .style("-moz-user-select", "none");

// Create edge elements (lines connecting nodes)
const link = svg.append("g")
      .attr("stroke", "#999")
      .attr("stroke-opacity", 0.6)
    .selectAll()
    .data(edges)
    .join("line")
      .attr("stroke-width", d => Math.sqrt(d.value))


// Create node elements (circles)
const node = svg.append("g")
      .attr("stroke", "#fff")
      .attr("stroke-width", 1.5)
    .selectAll()
    .data(nodes)
    .join("circle")
      .attr("r", 30)
      .attr("fill", "blue");

// Add tooltip that shows node name on hover
node.append("title")
      .text(d => d.name);

// Enable drag functionality for nodes
node.call(d3.drag()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended));


// Create text labels inside nodes
const text = svg.append("g")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "middle")
    .selectAll()
    .data(nodes)
    .join("text")
      .attr("font-size", "8px")
      .attr("fill", "white")
      .text(d => d.name);

/**
 * Called when drag starts
 * Reheats the simulation and locks the node position
 */
function dragstarted(event) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    event.subject.fx = event.subject.x;
    event.subject.fy = event.subject.y;
}

/**
 * Called while dragging
 * Updates node position to follow the mouse
 */
function dragged(event) {
    event.subject.fx = event.x;
    event.subject.fy = event.y;
}

/**
 * Called when drag ends
 * Cools down the simulation and releases the node position
 */
function dragended(event) {
    if (!event.active) simulation.alphaTarget(0);
    event.subject.fx = null;
    event.subject.fy = null;
}


/**
 * Force-directed simulation that positions nodes
 * - Links attract connected nodes (distance: 150px)
 * - Charge force repels all nodes from each other
 * - Center and X/Y forces gently pull everything toward the middle
 */
const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(edges).id(d => d.id).distance(150))
      .force("charge", d3.forceManyBody().strength(-400))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("x", d3.forceX(width / 2).strength(0.05))   // Pulls nodes toward center X
      .force("y", d3.forceY(height / 2).strength(0.05))  // Pulls nodes toward center Y
      .on("tick", ticked);

/**
 * Updates element positions on each simulation tick
 * This creates the animation effect as nodes move
 */
function ticked() {
    // Update edge positions based on connected node positions
    link
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);

    // Update node positions
    node
        .attr("cx", d => d.x)
        .attr("cy", d => d.y);

    // Update text label positions
    text
        .attr("x", d => d.x)
        .attr("y", d => d.y);
}