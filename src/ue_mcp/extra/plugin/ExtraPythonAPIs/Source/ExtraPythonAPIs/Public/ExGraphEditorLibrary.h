#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Engine/Blueprint.h"
#include "EdGraph/EdGraphNode.h"
#include "ExGraphEditorLibrary.generated.h"

/**
 * Blueprint Graph Editor Library for Python
 * Enables AI-driven Blueprint manipulation via Python scripts.
 *
 * Provides CRUD operations for Blueprint graph editing:
 * - CREATE: Create blueprints, add nodes (functions, events, variables, etc.)
 * - READ: Query nodes, pins, connections
 * - UPDATE: Connect nodes, set pin values, compile
 * - DELETE: Remove nodes, disconnect pins
 */
UCLASS()
class UExGraphEditorLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    // ========================================================================
    // CREATE Operations (Graph Node Creation)
    // For Blueprint creation, use BlueprintEditorLibrary.create_blueprint_asset_with_parent()
    // ========================================================================

    /**
     * Add a function call node to the Blueprint's event graph.
     * @param TargetBlueprint The Blueprint to modify
     * @param FunctionClass Class containing the function (e.g., UKismetSystemLibrary)
     * @param FunctionName Function name (e.g., "PrintString")
     * @param NodePosX X position in graph
     * @param NodePosY Y position in graph
     * @return The created node, or nullptr on failure
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static UEdGraphNode* AddCallFunctionNode(
        UBlueprint* TargetBlueprint,
        UClass* FunctionClass,
        FName FunctionName,
        int32 NodePosX = 0,
        int32 NodePosY = 0
    );

    /**
     * Add an event node (e.g., BeginPlay, Tick) to the Blueprint.
     * @param TargetBlueprint The Blueprint to modify
     * @param EventSignatureClass Class defining the event (e.g., AActor for BeginPlay)
     * @param EventName Event name (e.g., "ReceiveBeginPlay")
     * @param NodePosX X position in graph
     * @param NodePosY Y position in graph
     * @return The created event node, or nullptr on failure
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static UEdGraphNode* AddEventNode(
        UBlueprint* TargetBlueprint,
        UClass* EventSignatureClass,
        FName EventName,
        int32 NodePosX = 0,
        int32 NodePosY = 0
    );

    /**
     * Add a Branch (If) node to the Blueprint.
     * The Branch node has one input bool pin "Condition" and two output exec pins "True" and "False".
     * @param TargetBlueprint The Blueprint to modify
     * @param NodePosX X position in graph
     * @param NodePosY Y position in graph
     * @return The created Branch node, or nullptr on failure
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static UEdGraphNode* AddBranchNode(
        UBlueprint* TargetBlueprint,
        int32 NodePosX = 0,
        int32 NodePosY = 0
    );

    /**
     * Add a Variable Get node to read a Blueprint variable.
     * @param TargetBlueprint The Blueprint to modify
     * @param VariableName Name of the variable to get (must exist in Blueprint)
     * @param NodePosX X position in graph
     * @param NodePosY Y position in graph
     * @return The created VariableGet node, or nullptr on failure
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static UEdGraphNode* AddVariableGetNode(
        UBlueprint* TargetBlueprint,
        FName VariableName,
        int32 NodePosX = 0,
        int32 NodePosY = 0
    );

    /**
     * Add a Variable Set node to write a Blueprint variable.
     * @param TargetBlueprint The Blueprint to modify
     * @param VariableName Name of the variable to set (must exist in Blueprint)
     * @param NodePosX X position in graph
     * @param NodePosY Y position in graph
     * @return The created VariableSet node, or nullptr on failure
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static UEdGraphNode* AddVariableSetNode(
        UBlueprint* TargetBlueprint,
        FName VariableName,
        int32 NodePosX = 0,
        int32 NodePosY = 0
    );

    /**
     * Add a function call node by function name.
     * - If OwnerClass is nullptr: searches common library classes (PrintString, Delay, etc.)
     * - If OwnerClass is provided: searches only in that class (supports ANY class's member methods)
     *
     * For member methods, a Target/self pin is automatically created to receive the object instance.
     *
     * @param TargetBlueprint The Blueprint to modify
     * @param FunctionName Function name (e.g., "PrintString", "SetStaticMesh", "GetActorLocation")
     * @param OwnerClass Optional: the class containing the function (for member methods)
     * @param NodePosX X position in graph
     * @param NodePosY Y position in graph
     * @return The created node, or nullptr on failure
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static UEdGraphNode* AddFunctionNodeByName(
        UBlueprint* TargetBlueprint,
        const FString& FunctionName,
        UClass* OwnerClass = nullptr,
        int32 NodePosX = 0,
        int32 NodePosY = 0
    );

    // ========================================================================
    // UPDATE Operations
    // ========================================================================

    /**
     * Connect two nodes via their pins.
     * Supports fuzzy pin name matching (substring search).
     * @param NodeA Source node
     * @param PinNameA Source pin name (e.g., "then", "ReturnValue")
     * @param NodeB Target node
     * @param PinNameB Target pin name (e.g., "execute", "InString")
     * @return True if connection succeeded
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static bool ConnectNodes(
        UEdGraphNode* NodeA,
        const FString& PinNameA,
        UEdGraphNode* NodeB,
        const FString& PinNameB
    );

    /**
     * Set a pin's default literal value.
     * @param Node The node containing the pin
     * @param PinName Pin name
     * @param NewValue New default value as string
     * @return True if value was set successfully
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static bool SetPinDefaultValue(
        UEdGraphNode* Node,
        const FString& PinName,
        const FString& NewValue
    );

    // For Blueprint compilation, use BlueprintEditorLibrary.compile_blueprint()

    // ========================================================================
    // READ Operations (Graph Node Queries)
    // ========================================================================

    /**
     * Get all nodes in the Blueprint's event graph.
     * @param Blueprint The Blueprint to query
     * @return Array of all nodes in the event graph
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static TArray<UEdGraphNode*> GetAllNodes(UBlueprint* Blueprint);

    /**
     * Get all pin names for a node.
     * @param Node The node to query
     * @return Array of pin names with direction info (e.g., "In:execute", "Out:then")
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static TArray<FString> GetNodePinNames(UEdGraphNode* Node);

    /**
     * Get the node's display title.
     * @param Node The node to query
     * @return Node title string
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static FString GetNodeTitle(UEdGraphNode* Node);

    // For Blueprint variables, use BlueprintEditorLibrary.add_member_variable()

    // ========================================================================
    // DELETE Operations
    // ========================================================================

    /**
     * Delete a node from the Blueprint.
     * @param Blueprint The Blueprint containing the node
     * @param Node The node to delete
     * @return True if deletion succeeded
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static bool DeleteNode(UBlueprint* Blueprint, UEdGraphNode* Node);

    /**
     * Disconnect all links from a specific pin.
     * @param Node The node containing the pin
     * @param PinName Name of the pin to disconnect
     * @return True if disconnection succeeded
     */
    UFUNCTION(BlueprintCallable, Category = "ExtraPythonAPIs|Graph", meta = (DevelopmentOnly))
    static bool DisconnectPin(UEdGraphNode* Node, const FString& PinName);

private:
    /**
     * Helper: Get the event graph from a Blueprint, creating one if needed.
     */
    static UEdGraph* GetEventGraph(UBlueprint* Blueprint);

    /**
     * Helper: Find a pin by name with fuzzy matching support.
     */
    static UEdGraphPin* FindPinByName(UEdGraphNode* Node, const FString& PinName);
};
