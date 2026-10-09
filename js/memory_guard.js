import { app } from "../../scripts/app.js";

const NODE_NAME = "MemoryGuardChecker";

/*
 * สำคัญมาก:
 *
 * ห้ามใช้ "*" ตอน any_input ยังไม่ต่อ
 * เพราะ "*" = wildcard และ ComfyUI จะยอมให้ต่อกับอะไรก็ได้
 *
 * ใช้ type เฉพาะที่ไม่มี node ปกติใช้แทน
 */
const UNCONNECTED_TYPE =
    "__MEMORY_GUARD_UNCONNECTED__";


function normalizeType(type) {
    if (!type) {
        return "*";
    }

    if (Array.isArray(type)) {
        return type.length
            ? String(type[0])
            : "*";
    }

    return String(type);
}


function getInputSlot(node) {
    if (!node?.inputs) {
        return null;
    }

    return node.inputs.find(
        input =>
            input.name === "any_input"
    ) ?? null;
}


function getOutputSlot(node) {
    if (!node?.outputs) {
        return null;
    }

    return node.outputs.find(
        output =>
            output.name ===
            "output_passthrough"
    ) ?? null;
}


/*
 * หา type ที่ต่อเข้า any_input
 */
function getConnectedInputType(node) {
    const input =
        getInputSlot(node);

    if (
        !input ||
        input.link == null
    ) {
        return UNCONNECTED_TYPE;
    }

    const graph =
        node.graph;

    if (!graph) {
        return UNCONNECTED_TYPE;
    }

    const link =
        graph.links?.[input.link];

    if (!link) {
        return UNCONNECTED_TYPE;
    }

    /*
     * ปกติ link.type มีอยู่แล้ว
     */
    if (link.type) {
        return normalizeType(
            link.type
        );
    }

    /*
     * fallback:
     * อ่าน type จาก output ต้นทาง
     */
    const originNode =
        graph.getNodeById?.(
            link.origin_id
        );

    if (!originNode) {
        return UNCONNECTED_TYPE;
    }

    const originOutput =
        originNode.outputs?.[
            link.origin_slot
        ];

    if (!originOutput) {
        return UNCONNECTED_TYPE;
    }

    return normalizeType(
        originOutput.type
    );
}


/*
 * ตรวจ type compatibility
 */
function typesCompatible(
    sourceType,
    targetType
) {
    sourceType =
        normalizeType(sourceType);

    targetType =
        normalizeType(targetType);

    /*
     * ถ้าเป็น wildcard
     */
    if (
        sourceType === "*" ||
        targetType === "*"
    ) {
        return true;
    }

    /*
     * exact match
     */
    if (
        sourceType === targetType
    ) {
        return true;
    }

    /*
     * รองรับ union:
     * IMAGE,MASK
     */
    const sourceTypes =
        sourceType
            .split(",")
            .map(x => x.trim());

    const targetTypes =
        targetType
            .split(",")
            .map(x => x.trim());

    return sourceTypes.some(
        x =>
            targetTypes.includes(x)
    );
}


/*
 * ============================================================
 * เปลี่ยน output type
 * ============================================================
 */
function applyOutputType(
    node,
    type
) {
    const output =
        getOutputSlot(node);

    if (!output) {
        return;
    }

    type =
        normalizeType(type);

    node.properties ??= {};

    node.properties[
        "MemoryGuardInputType"
    ] = type;


    /*
     * นี่คือหัวใจของระบบ
     */
    output.type = type;
    output._type = type;


    /*
     * แสดง type บนชื่อ socket
     */
    if (
        type ===
        UNCONNECTED_TYPE
    ) {
        output.label =
            "output_passthrough (waiting)";
    } else {
        output.label =
            `output_passthrough (${type})`;
    }


    node.graph?.setDirtyCanvas?.(
        true,
        true
    );

    node.setDirtyCanvas?.(
        true,
        true
    );
}


/*
 * ============================================================
 * sync
 * ============================================================
 */
function syncType(node) {
    if (!node) {
        return;
    }

    const type =
        getConnectedInputType(node);

    applyOutputType(
        node,
        type
    );
}


/*
 * ============================================================
 * Extension
 * ============================================================
 */
app.registerExtension({

    name:
        "ComfyUI.MemoryGuard.DynamicType",


    async beforeRegisterNodeDef(
        nodeType,
        nodeData,
        app
    ) {

        if (
            nodeData.name !==
            NODE_NAME
        ) {
            return;
        }


        /*
         * =====================================================
         * BLOCK OUTPUT CONNECTION
         *
         * เรียกก่อนสร้าง link
         *
         * return false = ไม่สร้างสาย
         * =====================================================
         */
        const originalOnConnectOutput =
            nodeType.prototype
                .onConnectOutput;


        nodeType.prototype
            .onConnectOutput =
            function (
                outputIndex,
                inputType,
                inputSlot,
                targetNode,
                targetSlot
            ) {

                const output =
                    this.outputs?.[
                        outputIndex
                    ];


                /*
                 * สนใจเฉพาะ
                 * output_passthrough
                 */
                if (
                    !output ||
                    output.name !==
                        "output_passthrough"
                ) {
                    return (
                        originalOnConnectOutput
                            ? originalOnConnectOutput
                                .apply(
                                    this,
                                    arguments
                                )
                            : true
                    );
                }


                const outputType =
                    normalizeType(
                        output.type
                    );


                /*
                 * =================================================
                 * ยังไม่มี input
                 *
                 * ห้ามต่อ output เด็ดขาด
                 * =================================================
                 */
                if (
                    outputType ===
                    UNCONNECTED_TYPE
                ) {

                    console.warn(
                        "[MemoryGuard] " +
                        "Output is locked: " +
                        "any_input is not connected."
                    );

                    return false;
                }


                const targetType =
                    normalizeType(
                        inputSlot?.type
                    );


                /*
                 * =================================================
                 * ตรวจ type
                 * =================================================
                 */
                if (
                    !typesCompatible(
                        outputType,
                        targetType
                    )
                ) {

                    console.warn(
                        "[MemoryGuard] " +
                        `Blocked connection: ` +
                        `${outputType} -> ` +
                        `${targetType}`
                    );

                    return false;
                }


                /*
                 * ผ่าน
                 */
                if (
                    originalOnConnectOutput
                ) {
                    return originalOnConnectOutput
                        .apply(
                            this,
                            arguments
                        );
                }

                return true;
            };


        /*
         * =====================================================
         * INPUT CONNECTION CHANGE
         * =====================================================
         */
        const originalOnConnectionsChange =
            nodeType.prototype
                .onConnectionsChange;


        nodeType.prototype
            .onConnectionsChange =
            function (
                type,
                slotIndex,
                connected,
                linkInfo
            ) {

                originalOnConnectionsChange?.apply(
                    this,
                    arguments
                );


                /*
                 * รอให้ link state
                 * update ก่อน
                 */
                queueMicrotask(() => {
                    syncType(this);
                });


                /*
                 * second pass
                 */
                setTimeout(() => {
                    syncType(this);
                }, 0);
            };


        /*
         * =====================================================
         * NODE CREATED
         * =====================================================
         */
        const originalOnNodeCreated =
            nodeType.prototype
                .onNodeCreated;


        nodeType.prototype
            .onNodeCreated =
            function () {

                originalOnNodeCreated?.apply(
                    this,
                    arguments
                );


                this.properties ??= {};


                this.properties[
                    "MemoryGuardInputType"
                ] =
                    UNCONNECTED_TYPE;


                /*
                 * สำคัญ:
                 * output ต้อง lock ตั้งแต่สร้าง node
                 */
                const output =
                    getOutputSlot(this);

                if (output) {
                    output.type =
                        UNCONNECTED_TYPE;

                    output._type =
                        UNCONNECTED_TYPE;

                    output.label =
                        "output_passthrough (waiting)";
                }


                queueMicrotask(() => {
                    syncType(this);
                });
            };


        /*
         * =====================================================
         * CONFIGURE
         * =====================================================
         */
        const originalConfigure =
            nodeType.prototype
                .configure;


        nodeType.prototype
            .configure =
            function (data) {

                originalConfigure?.apply(
                    this,
                    arguments
                );


                queueMicrotask(() => {
                    syncType(this);
                });


                setTimeout(() => {
                    syncType(this);
                }, 0);
            };


        /*
         * =====================================================
         * BYPASS ON DELETE
         *
         * เก็บ source/target ก่อน node และ links ถูกลบ
         * แล้วเชื่อม source -> target หลังลบเสร็จ
         * =====================================================
         */
        const originalOnRemoved =
            nodeType.prototype.onRemoved;

        nodeType.prototype.onRemoved =
            function () {
                const node = this;
                const graph = node.graph;
                const input = getInputSlot(node);
                const output = getOutputSlot(node);
                const bypasses = [];

                if (graph && input && output) {
                    const inputLink =
                        input.link != null
                            ? graph.links?.[input.link]
                            : null;

                    const sourceNode =
                        inputLink
                            ? graph.getNodeById?.(inputLink.origin_id)
                            : null;

                    const sourceSlot = inputLink?.origin_slot;
                    const outputLinkIds =
                        Array.isArray(output.links)
                            ? [...output.links]
                            : [];

                    if (sourceNode && Number.isInteger(sourceSlot)) {
                        for (const linkId of outputLinkIds) {
                            const link = graph.links?.[linkId];
                            if (!link) continue;

                            const targetNode =
                                graph.getNodeById?.(link.target_id);

                            if (!targetNode || targetNode === node) continue;

                            bypasses.push({
                                sourceNode,
                                sourceSlot,
                                targetNode,
                                targetSlot: link.target_slot,
                            });
                        }
                    }
                }

                originalOnRemoved?.apply(this, arguments);

                if (!bypasses.length) return;

                // รอให้ LiteGraph ลบ node และ links เดิมเสร็จก่อน
                setTimeout(() => {
                    for (const bypass of bypasses) {
                        const {
                            sourceNode,
                            sourceSlot,
                            targetNode,
                            targetSlot,
                        } = bypass;

                        if (
                            !sourceNode.graph ||
                            !targetNode.graph ||
                            sourceNode.graph !== targetNode.graph
                        ) {
                            continue;
                        }

                        const sourceOutput =
                            sourceNode.outputs?.[sourceSlot];
                        const targetInput =
                            targetNode.inputs?.[targetSlot];

                        if (!sourceOutput || !targetInput) continue;

                        // ห้ามเขียนทับ connection ใหม่ที่ผู้ใช้สร้างไว้
                        if (targetInput.link != null) continue;

                        // เชื่อมใหม่เฉพาะเมื่อ type เข้ากันได้
                        if (
                            !typesCompatible(
                                sourceOutput.type,
                                targetInput.type
                            )
                        ) {
                            console.warn(
                                "[MemoryGuard] Skip bypass: incompatible types",
                                sourceOutput.type,
                                "->",
                                targetInput.type
                            );
                            continue;
                        }

                        try {
                            sourceNode.connect(
                                sourceSlot,
                                targetNode,
                                targetSlot
                            );
                        } catch (error) {
                            console.warn(
                                "[MemoryGuard] Auto-bypass failed:",
                                error
                            );
                        }
                    }

                    app.graph?.setDirtyCanvas?.(true, true);
                }, 0);
            };


        /*
         * =====================================================
         * ADDED
         * =====================================================
         */
        const originalOnAdded =
            nodeType.prototype
                .onAdded;


        nodeType.prototype
            .onAdded =
            function () {

                originalOnAdded?.apply(
                    this,
                    arguments
                );


                queueMicrotask(() => {
                    syncType(this);
                });


                setTimeout(() => {
                    syncType(this);
                }, 0);
            };
    },


    /*
     * =========================================================
     * ComfyUI nodeCreated
     * =========================================================
     */
    async nodeCreated(node) {

        if (
            node.comfyClass !==
            NODE_NAME
        ) {
            return;
        }


        queueMicrotask(() => {
            syncType(node);
        });


        setTimeout(() => {
            syncType(node);
        }, 0);
    },


    /*
     * =========================================================
     * หลังโหลด workflow
     * =========================================================
     */
    async afterConfigureGraph() {

        const graph =
            app.rootGraph;

        if (!graph) {
            return;
        }


        const nodes =
            graph._nodes ??
            graph.nodes ??
            [];


        for (const node of nodes) {

            if (
                node.comfyClass !==
                NODE_NAME
            ) {
                continue;
            }


            syncType(node);
        }
    },
});