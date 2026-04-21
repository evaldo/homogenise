/**
 * Fetches graph data from the Flask backend API
 * @returns {Object} Graph data containing nodes and edges
 */
async function loadGraph() {
    if (!window.PROJECT_ID) return { data: { nodes: [], edges: [] } };
    try {
        const response = await fetch(`/api/graph?project_id=${window.PROJECT_ID}`);
        const data = await response.json();
        if (!data.ok) throw new Error(data.error);
        return data;
    } catch (error) {
        console.error('Erro ao carregar grafo:', error);
        return { data: { nodes: [], edges: [] } };
    }
}

// ============================================================
// CONSTANTES DE LAYOUT
// ============================================================

const NODE_RADIUS = 75;
const LINK_DISTANCE = 450;        // distância ideal entre nós conectados
const CHARGE_STRENGTH = -1200;    // repulsão entre nós
const CENTER_STRENGTH = 0.03;     // força que puxa pro centro
const NODE_FONT_SIZE = "16px";    // tamanho da fonte dos labels dos nós
const EDGE_FONT_SIZE = 12;        // tamanho da fonte dos labels das arestas (número pra calcular padding)
const EDGE_LABEL_PADDING = 4;     // padding ao redor do texto do label

// Canvas dimensions
const width  = document.getElementById('graph-container').clientWidth;
const height = document.getElementById('graph-container').clientHeight;

let selectedId = null;

// Load graph data from API
var graph = await loadGraph()

// Transform nodes: add random initial positions
const nodes = graph.data.nodes.map(d => ({
    ...d,
    x: Math.random() * width,
    y: Math.random() * height
}))

const margin = 20;

// Transform edges: copy data as-is, descartando edges órfãos
const validNodeIds = new Set(nodes.map(n => n.id));
const edges = graph.data.edges
    .map(d => ({...d}))
    .filter(d => validNodeIds.has(d.source) && validNodeIds.has(d.target));

console.log("nodes:", nodes)
console.log("edges:", edges)

// Initialize SVG canvas and disable text selection
const svg = d3.select("#graph")
    .style("user-select", "none")
    .style("-webkit-user-select", "none")
    .style("-moz-user-select", "none");

// ============================================================
// ZOOM & PAN
// ============================================================

// Grupo container para aplicar o transform de zoom
const zoomG = svg.append("g").attr("id", "zoom-container");

// Configura o behavior de zoom
const zoom = d3.zoom()
    .scaleExtent([0.1, 4])      // limites: 10% até 400%
    .on("zoom", (event) => {
        zoomG.attr("transform", event.transform);
    });

// Aplica o zoom no SVG
svg.call(zoom);

// Desabilita double-click zoom (evita conflito com seleção)
svg.on("dblclick.zoom", null);

// Funções utilitárias de zoom
function zoomIn() {
    svg.transition().duration(300).call(zoom.scaleBy, 1.3);
}

function zoomOut() {
    svg.transition().duration(300).call(zoom.scaleBy, 0.7);
}

function zoomReset() {
    svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
}

function zoomFit() {
    const bounds = zoomG.node().getBBox();
    if (bounds.width === 0 || bounds.height === 0) return;

    const fullWidth = width;
    const fullHeight = height;
    const widthScale = fullWidth / bounds.width;
    const heightScale = fullHeight / bounds.height;
    const scale = Math.min(widthScale, heightScale) * 0.85; // 85% pra dar margem
    const tx = (fullWidth - bounds.width * scale) / 2 - bounds.x * scale;
    const ty = (fullHeight - bounds.height * scale) / 2 - bounds.y * scale;

    svg.transition()
        .duration(750)
        .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
}

// ============================================================
// GRUPOS SVG (dentro do zoomG para zoom funcionar)
// ============================================================

// Groups SVG — ordem importa para layering
const linkG       = zoomG.append("g").attr("stroke-opacity", 0.6);
const linkLabelBgG = zoomG.append("g").attr("pointer-events", "none"); // fundo dos labels
const linkLabelG  = zoomG.append("g").attr("pointer-events", "none");
const nodeG       = zoomG.append("g").attr("stroke", "#fff").attr("stroke-width", 1.5);
const textG       = zoomG.append("g").attr("text-anchor", "middle").attr("dominant-baseline", "middle");

// Referências vivas para as seleções D3
let link, linkLabel, linkLabelBg, node, text;

/**
 * Re-renderiza links, nós e textos a partir dos arrays `edges` e `nodes`.
 */
function redrawGraph() {
    // --- Links ---
    link = linkG.selectAll("line")
        .data(edges, d => {
            const s = d.source?.id ?? d.source;
            const t = d.target?.id ?? d.target;
            return `${s}--${t}--${d.label}`;
        })
        .join(
            enter => enter.append("line"),
            update => update,
            exit   => exit.remove()
        )
        .attr("stroke", d => {
            if (d.__preview === "remove") return "#f85149";
            if (d.__preview === "add")    return "#3fb950";
            return "#999";
        })
        .attr("stroke-dasharray", d => {
            if (d.__preview === "remove") return "6,4";
            if (d.__preview === "add")    return "4,4";
            return null;
        })
        .attr("stroke-width", d => d.__preview ? 2 : Math.sqrt(d.value || 1));

    // --- Labels das arestas (com fundo que "corta" a linha) ---
    const STRUCTURAL = new Set(["subClassOf", "domain", "range"]);
    const edgesWithLabels = edges.filter(d => !STRUCTURAL.has(d.label));

    // Backgrounds (retângulos que cobrem a linha)
    linkLabelBg = linkLabelBgG.selectAll("rect")
        .data(edgesWithLabels, d => {
            const s = d.source?.id ?? d.source;
            const t = d.target?.id ?? d.target;
            return `${s}--${t}--${d.label}`;
        })
        .join("rect")
        .attr("fill", "white")
        .attr("rx", 3)
        .attr("ry", 3);

    // Textos dos labels
    linkLabel = linkLabelG.selectAll("text")
        .data(edgesWithLabels, d => {
            const s = d.source?.id ?? d.source;
            const t = d.target?.id ?? d.target;
            return `${s}--${t}--${d.label}`;
        })
        .join("text")
        .attr("font-size", `${EDGE_FONT_SIZE}px`)
        .attr("text-anchor", "middle")
        .attr("dominant-baseline", "middle")
        .attr("fill", d => {
            if (d.__preview === "remove") return "#f85149";
            if (d.__preview === "add")    return "#3fb950";
            return "#333";
        })
        .attr("stroke", "none")
        .text(d => d.label);

    node = nodeG.selectAll("circle")
        .data(nodes, d => d.id)
        .join(
            enter => {
                const c = enter.append("circle")
                    .attr("r", NODE_RADIUS)
                    .call(d3.drag()
                        .on("start", dragstarted)
                        .on("drag",  dragged)
                        .on("end",   dragended))
                    .on("click", (event, d) => {
                        event.stopPropagation();
                        selectedId = selectedId === d.id ? null : d.id;
                        highlightGraph(selectedId);
                        highlightTree(selectedId);
                    });
                c.append("title").text(d => d.name);
                return c;
            },
            update => update,
            exit   => exit.remove()
        )
        .attr("fill", d => {
            if (d.__preview === "remove") return "#f85149";
            if (d.__preview === "add")    return "#3fb950";
            return "blue";
        });

    // --- Textos com word wrap ---
    text = textG.selectAll("text")
        .data(nodes, d => d.id)
        .join("text")
        .attr("font-size", NODE_FONT_SIZE)
        .attr("font-weight", "500")
        .attr("fill", "white")
        .attr("text-anchor", "middle")
        .attr("dominant-baseline", "middle")
        .each(function(d) {
            const text = d3.select(this);
            text.selectAll("tspan").remove();

            const words = wrapText(d.name, NODE_RADIUS * 1.6);
            const lineHeight = 1.2; // em
            const totalLines = words.length;
            const startOffset = -(totalLines - 1) / 2;

            words.forEach((line, i) => {
                text.append("tspan")
                    .attr("x", 0)
                    .attr("dy", i === 0 ? `${startOffset * lineHeight}em` : `${lineHeight}em`)
                    .text(line);
            });
        });
}

/**
 * Quebra texto em linhas que cabem dentro de uma largura máxima.
 * @param {string} text - Texto a quebrar
 * @param {number} maxWidth - Largura máxima em pixels
 * @returns {string[]} Array de linhas
 */
function wrapText(text, maxWidth) {
    // Primeiro, quebra camelCase e PascalCase em palavras separadas
    // "AnimalDomestico" -> "Animal Domestico"
    const expanded = text
        .replace(/([a-z])([A-Z])/g, '$1 $2')  // camelCase
        .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2');  // ABCDef -> ABC Def

    const words = expanded.split(/[\s_-]+/); // quebra em espaço, underscore ou hífen
    const charWidth = 7; // largura média por caractere (diminuí pra caber mais)
    const maxChars = Math.floor(maxWidth / charWidth);

    const lines = [];
    let currentLine = '';

    for (const word of words) {
        const testLine = currentLine ? `${currentLine} ${word}` : word;

        if (testLine.length <= maxChars) {
            currentLine = testLine;
        } else {
            if (currentLine) lines.push(currentLine);

            // Se a palavra sozinha é maior que o máximo, quebra forçado
            if (word.length > maxChars) {
                let remaining = word;
                while (remaining.length > maxChars) {
                    lines.push(remaining.slice(0, maxChars - 1) + '-');
                    remaining = remaining.slice(maxChars - 1);
                }
                currentLine = remaining;
            } else {
                currentLine = word;
            }
        }
    }

    if (currentLine) lines.push(currentLine);

    // Limita a 4 linhas pra não estourar o círculo
    if (lines.length > 4) {
        lines.length = 4;
        lines[3] = lines[3].slice(0, -1) + '…';
    }

    return lines;
}

// Render inicial
redrawGraph();

// Click no fundo deseleciona (ignora se foi pan/drag)
svg.on("click", (event) => {
    if (event.defaultPrevented) return;
    selectedId = null;
    highlightGraph(null);
    highlightTree(null);
});

// ============================================================
// SISTEMA DE PREVIEW (diff estilo GitHub)
// ============================================================

let pendingActions = [];

/**
 * Marca edges/nós existentes como "remover" (vermelho)
 * e injeta edges/nós novos como "adicionar" (verde).
 */
function previewActions(actions) {
    discardPreview();
    pendingActions = actions;

    const nameToId = new Map(nodes.map(n => [n.name, n.id]));
    const validIds = new Set(nodes.map(n => n.id));

    for (const { type, payload, reason } of actions) {
        if (type === "removeEdge") {
            const srcId = nameToId.get(payload.source) ?? payload.source;
            const tgtId = nameToId.get(payload.target) ?? payload.target;

            const edge = edges.find(e => {
                const s = e.source?.id ?? e.source;
                const t = e.target?.id ?? e.target;
                return s === srcId && t === tgtId && e.label === payload.label;
            });
            if (edge) edge.__preview = "remove";
            else console.warn("removeEdge: aresta não encontrada →", payload);

        } else if (type === "createEdge") {
            const srcId = nameToId.get(payload.source) ?? payload.source;
            const tgtId = nameToId.get(payload.target) ?? payload.target;

            if (!validIds.has(srcId) || !validIds.has(tgtId)) {
                console.warn("createEdge ignorado: nó não encontrado →", payload, { srcId, tgtId });
                continue;
            }

            const already = edges.find(e => {
                const s = e.source?.id ?? e.source;
                const t = e.target?.id ?? e.target;
                return s === srcId && t === tgtId && e.label === payload.label;
            });
            if (!already) {
                edges.push({
                    source:    srcId,
                    target:    tgtId,
                    label:     payload.label,
                    __preview: "add"
                });
            }

        } else if (type === "removeNode") {
            const candidates = [payload.id, payload.label, payload.name, payload.target, payload.source]
                .filter(Boolean);

            let n = nodes.find(n =>
                candidates.some(c => c === n.id || c === n.name)
            );

            if (!n) {
                const haystack = [payload.label, payload.reason, payload.target, reason]
                    .filter(Boolean).join(" ");
                n = nodes.find(n => n.name && haystack.includes(n.name));
            }

            if (n) {
                n.__preview = "remove";
                console.log("removeNode: encontrado →", n.name);
            } else {
                console.warn("removeNode: nó não encontrado →", payload);
            }

        } else if (type === "createNode") {
            const newNode = {
                id:        payload.id,
                name:      payload.label ?? payload.id,
                type:      payload.type ?? 'Class',
                x:         width  / 2 + (Math.random() - 0.5) * 100,
                y:         height / 2 + (Math.random() - 0.5) * 100,
                __preview: "add"
            };
            nodes.push(newNode);

            nameToId.set(newNode.name, newNode.id);
            validIds.add(newNode.id);
        }
    }

    simulation.nodes(nodes);
    simulation.force("link", d3.forceLink(edges).id(d => d.id).distance(LINK_DISTANCE));
    simulation.alpha(0.3).restart();

    rebuildRoot();
    redrawGraph();
    updateTree();
    setPreviewToolbar(true);
}

/**
 * Aplica de verdade as ações que ainda estão com __preview ativo.
 */
function commitActions() {
    for (let i = edges.length - 1; i >= 0; i--) {
        if (edges[i].__preview === "remove") edges.splice(i, 1);
    }

    for (let i = nodes.length - 1; i >= 0; i--) {
        if (nodes[i].__preview === "remove") nodes.splice(i, 1);
    }

    edges.forEach(e => delete e.__preview);
    nodes.forEach(n => delete n.__preview);

    pendingActions = [];
    simulation.nodes(nodes);
    simulation.force("link", d3.forceLink(edges).id(d => d.id).distance(LINK_DISTANCE));
    simulation.alpha(0.3).restart();
    rebuildRoot();
    redrawGraph();
    updateTree();
    setPreviewToolbar(false);
}

/**
 * Descarta o preview sem aplicar nada.
 */
function discardPreview() {
    for (let i = edges.length - 1; i >= 0; i--) {
        if (edges[i].__preview === "add") edges.splice(i, 1);
    }

    for (let i = nodes.length - 1; i >= 0; i--) {
        if (nodes[i].__preview === "add") nodes.splice(i, 1);
    }

    edges.forEach(e => delete e.__preview);
    nodes.forEach(n => delete n.__preview);

    pendingActions = [];
    simulation.force("link", d3.forceLink(edges).id(d => d.id).distance(LINK_DISTANCE));
    simulation.alpha(0.1).restart();
    rebuildRoot();
    redrawGraph();
    updateTree();
    setPreviewToolbar(false);
}

/**
 * Mostra/esconde a toolbar de confirmação de preview.
 */
function setPreviewToolbar(visible) {
    const toolbar = document.getElementById('preview-toolbar');
    if (!toolbar) return;
    toolbar.classList.toggle('d-none', !visible);
    toolbar.classList.toggle('d-flex', visible);

    if (visible) {
        const list = document.getElementById('preview-action-list');
        if (list) {
            list.innerHTML = pendingActions.map(({ type, payload, reason }, i) => {
                const color  = type.startsWith("remove") ? "#f85149" : "#3fb950";
                const icon   = type.startsWith("remove") ? "−" : "+";
                const label  = payload.source ?? payload.id ?? '';
                const target = payload.target ?? '';
                const lbl    = payload.label ? `[${payload.label}]` : '';
                return `
                    <li style="display:flex; align-items:flex-start; gap:8px; margin-bottom:8px;">
                        <input type="checkbox" id="action-${i}" checked
                            data-index="${i}"
                            style="margin-top:2px; accent-color:${color}; cursor:pointer; flex-shrink:0;">
                        <label for="action-${i}" style="cursor:pointer;">
                            <span style="color:${color};">
                                <strong>${icon} ${type}</strong>
                                <span style="color:#ccc;"> — ${label}${target ? ' → ' + target : ''} ${lbl}</span>
                            </span>
                            ${reason ? `<br><small style="color:#8b949e;">${reason}</small>` : ''}
                        </label>
                    </li>`;
            }).join('');

            list.querySelectorAll('input[type=checkbox]').forEach(cb => {
                cb.addEventListener('change', () => {
                    const action = pendingActions[parseInt(cb.dataset.index)];
                    if (!action) return;
                    const { type, payload } = action;
                    const nameToId = new Map(nodes.map(n => [n.name, n.id]));
                    const validIds = new Set(nodes.map(n => n.id));

                    if (type === "removeEdge") {
                        const srcId = nameToId.get(payload.source) ?? payload.source;
                        const tgtId = nameToId.get(payload.target) ?? payload.target;
                        const edge = edges.find(e => {
                            const s = e.source?.id ?? e.source;
                            const t = e.target?.id ?? e.target;
                            return s === srcId && t === tgtId && e.label === payload.label;
                        });
                        if (edge) edge.__preview = cb.checked ? "remove" : undefined;

                    } else if (type === "createEdge") {
                        const srcId = nameToId.get(payload.source) ?? payload.source;
                        const tgtId = nameToId.get(payload.target) ?? payload.target;

                        if (!validIds.has(srcId) || !validIds.has(tgtId)) {
                            console.warn("createEdge (checkbox) ignorado: nó não encontrado →", payload);
                            return;
                        }

                        const edge = edges.find(e => {
                            const s = e.source?.id ?? e.source;
                            const t = e.target?.id ?? e.target;
                            return s === srcId && t === tgtId && e.label === payload.label;
                        });
                        if (cb.checked) {
                            if (edge) edge.__preview = "add";
                            else edges.push({ source: srcId, target: tgtId, label: payload.label, __preview: "add" });
                        } else {
                            if (edge) edges.splice(edges.indexOf(edge), 1);
                        }

                    } else if (type === "removeNode") {
                        const n = nodes.find(n => n.id === payload.id || n.name === payload.id || n.name === payload.label);
                        if (n) n.__preview = cb.checked ? "remove" : undefined;

                    } else if (type === "createNode") {
                        const n = nodes.find(n => n.id === payload.id);
                        if (cb.checked) {
                            if (n) n.__preview = "add";
                            else nodes.push({ id: payload.id, name: payload.label ?? payload.id, x: width/2, y: height/2, __preview: "add" });
                        } else {
                            if (n) nodes.splice(nodes.indexOf(n), 1);
                        }
                    }

                    simulation.nodes(nodes);
                    simulation.force("link", d3.forceLink(edges).id(d => d.id).distance(LINK_DISTANCE));
                    simulation.alpha(0.1).restart();
                    rebuildRoot();
                    redrawGraph();
                    updateTree();
                });
            });
        }
    }
}

// ============================================================
// DRAG
// ============================================================

function dragstarted(event) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    event.subject.fx = event.subject.x;
    event.subject.fy = event.subject.y;
}

function dragged(event) {
    event.subject.fx = event.x;
    event.subject.fy = event.y;
}

function dragended(event) {
    if (!event.active) simulation.alphaTarget(0);
    event.subject.fx = null;
    event.subject.fy = null;
}

// ============================================================
// SIMULAÇÃO
// ============================================================

const simulation = d3.forceSimulation(nodes)
    .force("link",   d3.forceLink(edges).id(d => d.id).distance(LINK_DISTANCE))
    .force("charge", d3.forceManyBody().strength(CHARGE_STRENGTH))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("x",      d3.forceX(width  / 2).strength(CENTER_STRENGTH))
    .force("y",      d3.forceY(height / 2).strength(CENTER_STRENGTH))
    .force("collide", d3.forceCollide().radius(NODE_RADIUS + 10).strength(0.7))
    .on("tick", ticked);

function ticked() {
    link
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);

    // Posiciona labels das arestas com rotação alinhada à linha
    linkLabel
        .attr("transform", d => {
            const mx = (d.source.x + d.target.x) / 2;
            const my = (d.source.y + d.target.y) / 2;
            let angle = Math.atan2(d.target.y - d.source.y, d.target.x - d.source.x) * 180 / Math.PI;
            // Evita texto de cabeça pra baixo
            if (angle > 90) angle -= 180;
            if (angle < -90) angle += 180;
            return `translate(${mx},${my}) rotate(${angle})`;
        });

    // Posiciona backgrounds dos labels
    linkLabelBg.each(function(d) {
        const textEl = linkLabel.filter(t => {
            const ts = t.source?.id ?? t.source;
            const tt = t.target?.id ?? t.target;
            const ds = d.source?.id ?? d.source;
            const dt = d.target?.id ?? d.target;
            return ts === ds && tt === dt && t.label === d.label;
        }).node();

        if (textEl) {
            const bbox = textEl.getBBox();
            const mx = (d.source.x + d.target.x) / 2;
            const my = (d.source.y + d.target.y) / 2;
            let angle = Math.atan2(d.target.y - d.source.y, d.target.x - d.source.x) * 180 / Math.PI;
            if (angle > 90) angle -= 180;
            if (angle < -90) angle += 180;

            d3.select(this)
                .attr("width", bbox.width + EDGE_LABEL_PADDING * 2)
                .attr("height", bbox.height + EDGE_LABEL_PADDING * 2)
                .attr("transform", `translate(${mx},${my}) rotate(${angle})`)
                .attr("x", -bbox.width / 2 - EDGE_LABEL_PADDING)
                .attr("y", -bbox.height / 2 - EDGE_LABEL_PADDING);
        }
    });

    node
        .attr("cx", d => d.x)
        .attr("cy", d => d.y);

    text
        .attr("transform", d => `translate(${d.x},${d.y})`);
}

// ============================================================
// HIGHLIGHT
// ============================================================

function getHiddenIds() {
    const hidden = new Set();
    root.each(d => {
        if (d._children) {
            d._children.forEach(child => {
                child.each(c => hidden.add(c.data.id));
            });
        }
    });
    return hidden;
}

function highlightGraph(id) {
    const hidden = getHiddenIds();
    node
        .attr("fill", d => {
            if (hidden.has(d.id)) return "transparent";
            if (d.__preview === "remove") return "#f85149";
            if (d.__preview === "add")    return "#3fb950";
            return d.id === id ? "orange" : "blue";
        })
        .attr("pointer-events", d => hidden.has(d.id) ? "none" : "all");
    text.attr("opacity", d => hidden.has(d.id) ? 0 : 1);
    link.attr("opacity", d => (hidden.has(d.source.id) || hidden.has(d.target.id)) ? 0 : 1);
    linkLabel.attr("opacity", d => (hidden.has(d.source.id) || hidden.has(d.target.id)) ? 0 : 1);
    linkLabelBg.attr("opacity", d => (hidden.has(d.source.id) || hidden.has(d.target.id)) ? 0 : 1);
}

// ============================================================
// ÁRVORE INDENTADA
// ============================================================

function buildTree(apiData) {
    const nodes = apiData.data.nodes;
    const edges = apiData.data.edges;

    // Se não tem nós, retorna raiz vazia
    if (!nodes || nodes.length === 0) {
        return { id: "__root__", name: "Ontologia", children: [] };
    }

    const nodeMap = new Map();
    nodes.forEach(n => nodeMap.set(n.id, { id: n.id, name: n.name, children: [] }));

    const subClassEdges = edges.filter(e => e.label === "subClassOf");
    subClassEdges.forEach(e => {
        const pai   = nodeMap.get(e.target);
        const filho = nodeMap.get(e.source);
        if (pai && filho) pai.children.push(filho);
    });

    const temPai = new Set(subClassEdges.map(e => e.source));
    const raizes = nodes
        .filter(n => n.type === "Class" && !temPai.has(n.id))
        .map(n => nodeMap.get(n.id));

    if (raizes.length === 0 && nodes.length > 0) {
        const allNodes = nodes
            .filter(n => n.type === "Class")
            .map(n => nodeMap.get(n.id))
            .filter(Boolean);
        return { id: "__root__", name: "Ontologia", children: allNodes };
    }

    if (raizes.length === 1) return raizes[0];
    return { id: "__root__", name: "Ontologia", children: raizes };
}

function buildTreeFromLive() {
    // Se não tem nós, retorna uma raiz vazia válida
    if (!nodes || nodes.length === 0) {
        return { id: "__root__", name: "Ontologia", children: [] };
    }

    const nodeMap = new Map();
    nodes.forEach(n => nodeMap.set(n.id, {
        id:        n.id,
        name:      n.name,
        type:      n.type,
        __preview: n.__preview,
        children:  []
    }));

    const subClassEdges = edges.filter(e => {
        if (e.label !== "subClassOf") return false;
        if (e.__preview === "remove") return false;
        const srcId = e.source?.id ?? e.source;
        const tgtId = e.target?.id ?? e.target;
        return nodeMap.has(srcId) && nodeMap.has(tgtId);
    });

    subClassEdges.forEach(e => {
        const srcId = e.source?.id ?? e.source;
        const tgtId = e.target?.id ?? e.target;
        const pai   = nodeMap.get(tgtId);
        const filho = nodeMap.get(srcId);
        if (pai && filho) {
            if (!pai.children.find(c => c.id === filho.id)) {
                pai.children.push(filho);
            }
        }
    });

    const temPai = new Set(subClassEdges.map(e => e.source?.id ?? e.source));
    const raizes = nodes
        .filter(n => n.type === "Class" && !temPai.has(n.id))
        .map(n => nodeMap.get(n.id))
        .filter(Boolean);

    // Se não tem raízes mas tem nós, retorna raiz com todos
    if (raizes.length === 0 && nodes.length > 0) {
        const allNodes = nodes
            .filter(n => n.type === "Class")
            .map(n => nodeMap.get(n.id))
            .filter(Boolean);
        return { id: "__root__", name: "Ontologia", children: allNodes };
    }

    if (raizes.length === 1) return raizes[0];
    return { id: "__root__", name: "Ontologia", children: raizes };
}

function rebuildRoot() {
    const collapsedIds = new Set();
    if (root) {
        root.each(d => { if (d._children) collapsedIds.add(d.data.id); });
    }

    root = d3.hierarchy(buildTreeFromLive());

    root.each(d => {
        if (collapsedIds.has(d.data.id) && d.children) {
            d._children = d.children;
            d.children  = null;
        }
    });
}

const treeNodeSize = 17;
const treeWidth    = document.getElementById('tree-container').clientWidth - 10;

const tree      = d3.select("#tree");
const treeLinkG = tree.append("g").attr("fill", "none").attr("stroke", "#999");
const treeNodeG = tree.append("g");

function updateTree() {
    root.eachBefore((i => d => d.index = i++)(0));
    const treeNodes  = root.descendants();
    const treeHeight = (treeNodes.length + 1) * treeNodeSize;

    tree
        .attr("width",   treeWidth)
        .attr("height",  treeHeight)
        .attr("viewBox", [-treeNodeSize / 2, -treeNodeSize * 3 / 2, treeWidth, treeHeight]);

    const previewMap = new Map(nodes.map(n => [n.id, n.__preview]));

    treeLinkG.selectAll("path")
        .data(root.links(), d => d.target.data.id)
        .join("path")
        .attr("stroke", d => {
            const srcId = d.target.data.id;
            const tgtId = d.source.data.id;
            const edge  = edges.find(e => {
                const s = e.source?.id ?? e.source;
                const t = e.target?.id ?? e.target;
                return s === srcId && t === tgtId && e.label === "subClassOf";
            });
            if (edge?.__preview === "remove") return "#f85149";
            if (edge?.__preview === "add")    return "#3fb950";
            return "#999";
        })
        .attr("stroke-dasharray", d => {
            const srcId = d.target.data.id;
            const tgtId = d.source.data.id;
            const edge  = edges.find(e => {
                const s = e.source?.id ?? e.source;
                const t = e.target?.id ?? e.target;
                return s === srcId && t === tgtId && e.label === "subClassOf";
            });
            return edge?.__preview ? "4,4" : null;
        })
        .attr("d", d => `
            M${d.source.depth * treeNodeSize},${d.source.index * treeNodeSize}
            V${d.target.index * treeNodeSize}
            h${treeNodeSize}
        `);

    const treeNode = treeNodeG.selectAll("g")
        .data(treeNodes, d => d.data.id)
        .join("g")
        .attr("font-size",   "20px")
        .attr("font-family", "'Gill Sans', 'Helvetica Neue', Helvetica, sans-serif")
        .attr("transform",   d => `translate(0,${d.index * treeNodeSize})`);

    treeNode.selectAll("text.arrow").remove();
    treeNode.filter(d => (d.children || d._children) && d.data.id !== "__root__")
        .append("text")
        .attr("class",    "arrow")
        .attr("x",        d => d.depth * treeNodeSize - 12)
        .attr("dy",       "0.32em")
        .attr("font-size","10px")
        .attr("fill", d => {
            const preview = previewMap.get(d.data.id);
            if (preview === "remove") return "#f85149";
            if (preview === "add")    return "#3fb950";
            return "#999";
        })
        .style("cursor",  "pointer")
        .text(d => d.children ? "▼" : "▶")
        .on("click", (event, d) => {
            event.stopPropagation();
            if (d.children) { d._children = d.children; d.children = null; }
            else             { d.children = d._children; d._children = null; }
            updateTree();
            highlightGraph(selectedId);
        });

    treeNode.selectAll("circle")
        .data(d => [d])
        .join("circle")
        .attr("cx",   d => d.depth * treeNodeSize)
        .attr("r",    2.5)
        .attr("fill", d => {
            const preview = previewMap.get(d.data.id);
            if (preview === "remove") return "#f85149";
            if (preview === "add")    return "#3fb950";
            return d.data.id === selectedId ? "orange" : (d.children ? "#e6edf3" : "#999");
        });

    treeNode.selectAll("text.label")
        .data(d => [d])
        .join("text")
        .attr("class",       "label")
        .attr("dy",          "0.32em")
        .attr("x",           d => d.depth * treeNodeSize + 6)
        .attr("font-weight", d => d.data.id === selectedId ? "bold" : "normal")
        .attr("fill", d => {
            const preview = previewMap.get(d.data.id);
            if (preview === "remove") return "#f85149";
            if (preview === "add")    return "#3fb950";
            return d.data.id === selectedId ? "orange" : "#e6edf3";
        })
        .text(d => d.data.name)
        .on("click", (event, d) => {
            event.stopPropagation();
            if (d.data.id === "__root__") return;
            selectedId = selectedId === d.data.id ? null : d.data.id;
            highlightGraph(selectedId);
            highlightTree(selectedId);
        });

    treeNode.append("title")
        .text(d => d.ancestors().reverse().map(d => d.data.name).join("/"));
}

function highlightTree(id) {
    updateTree();
}

// ============================================================
// SUGESTÕES DA IA
// ============================================================

async function getSuggestions() {
    const btn = document.getElementById('suggest-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '⏳ Gerando...';
    }

    try {
        const response = await fetch("/api/suggest", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify(graph.data)
        });
        const data = await response.json();

        if (!data.ok) {
            console.error("Erro nas sugestões:", data);
            return;
        }

        if (!data.actions?.length) {
            console.log("Nenhuma sugestão retornada.");
            return;
        }

        console.log("Sugestões recebidas:", data.actions);
        previewActions(data.actions);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<img src="/static/imgs/ollama.svg" alt="" width="32" height="32" style="filter:invert(1)"><br>Get Suggestions By AI';
        }
    }
}

// ============================================================
// EXPORT OWL (via backend com Owlready2)
// ============================================================

async function exportOWL() {
    const btn = document.querySelector('[onclick="exportOWL()"]');
    const originalText = btn?.innerHTML;

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '⏳ Exportando...';
    }

    try {
        // Monta payload normalizado
        const payload = {
            nodes: nodes.map(n => ({
                id: n.id,
                name: n.name,
                type: n.type ?? 'Class'
            })),
            edges: edges.map(e => ({
                source: e.source?.id ?? e.source,
                target: e.target?.id ?? e.target,
                label: e.label
            })),
            name: 'evaldo_ontology',
            iri: 'http://evaldo.example.org/ontology#'
        };

        const response = await fetch('/api/export/owl', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            let errMsg = response.statusText;
            try {
                const err = await response.json();
                errMsg = err.error ?? errMsg;
            } catch {}
            alert('Erro ao exportar: ' + errMsg);
            return;
        }

        // Dispara download
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'evaldo.owl';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

// ============================================================
// EXPORTS GLOBAIS
// ============================================================

window.getSuggestions  = getSuggestions;
window.previewActions  = previewActions;
window.commitActions   = commitActions;
window.discardPreview  = discardPreview;
window.exportOWL       = exportOWL;
window._evaldoNodes    = nodes;
window._evaldoEdges    = edges;
window.graph           = graph;

// Zoom controls
window.zoomIn    = zoomIn;
window.zoomOut   = zoomOut;
window.zoomReset = zoomReset;
window.zoomFit   = zoomFit;

// ============================================================
// INIT
// ============================================================

let root = d3.hierarchy(buildTree(graph));
updateTree();