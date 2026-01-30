#include "ExGraphEditorLibrary.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "AssetToolsModule.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_CallFunction.h"
#include "K2Node_Event.h"
#include "K2Node_CustomEvent.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "Factories/BlueprintFactory.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetMathLibrary.h"
#include "Kismet/KismetStringLibrary.h"
#include "Kismet/KismetArrayLibrary.h"
#include "Kismet/KismetTextLibrary.h"

DEFINE_LOG_CATEGORY_STATIC(LogExGraphEditor, Log, All);

// ============================================================================
// Private Helpers
// ============================================================================

UEdGraph* UExGraphEditorLibrary::GetEventGraph(UBlueprint* Blueprint)
{
    if (!Blueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("GetEventGraph: Blueprint is null"));
        return nullptr;
    }

    UEdGraph* Graph = FBlueprintEditorUtils::FindEventGraph(Blueprint);
    if (!Graph)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("GetEventGraph: No event graph found for Blueprint '%s'"), *Blueprint->GetName());
    }
    return Graph;
}

UEdGraphPin* UExGraphEditorLibrary::FindPinByName(UEdGraphNode* Node, const FString& PinName)
{
    if (!Node)
    {
        return nullptr;
    }

    // Try exact match first
    UEdGraphPin* Pin = Node->FindPin(FName(*PinName));
    if (Pin)
    {
        return Pin;
    }

    // Fuzzy match: find pin containing the search term
    for (UEdGraphPin* P : Node->Pins)
    {
        if (P->PinName.ToString().Contains(PinName))
        {
            return P;
        }
    }

    return nullptr;
}

// ============================================================================
// CREATE Operations (Graph Nodes)
// For Blueprint creation, use BlueprintEditorLibrary.create_blueprint_asset_with_parent()
// ============================================================================

UEdGraphNode* UExGraphEditorLibrary::AddCallFunctionNode(
    UBlueprint* TargetBlueprint,
    UClass* FunctionClass,
    FName FunctionName,
    int32 NodePosX,
    int32 NodePosY)
{
    if (!TargetBlueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddCallFunctionNode: TargetBlueprint is null"));
        return nullptr;
    }

    if (!FunctionClass)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddCallFunctionNode: FunctionClass is null"));
        return nullptr;
    }

    UEdGraph* Graph = GetEventGraph(TargetBlueprint);
    if (!Graph)
    {
        return nullptr;
    }

    // Find the UFunction
    UFunction* TargetFunc = FunctionClass->FindFunctionByName(FunctionName);
    if (!TargetFunc)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddCallFunctionNode: Function '%s' not found in class '%s'"),
            *FunctionName.ToString(), *FunctionClass->GetName());
        return nullptr;
    }

    // Create the node
    UK2Node_CallFunction* NewNode = NewObject<UK2Node_CallFunction>(Graph);
    NewNode->CreateNewGuid();
    NewNode->NodePosX = NodePosX;
    NewNode->NodePosY = NodePosY;

    // Set up the function reference
    NewNode->SetFromFunction(TargetFunc);

    // Add to graph and create pins
    Graph->AddNode(NewNode, false, false);
    NewNode->AllocateDefaultPins();

    // Notify changes
    Graph->NotifyGraphChanged();
    FBlueprintEditorUtils::MarkBlueprintAsModified(TargetBlueprint);

    UE_LOG(LogExGraphEditor, Log, TEXT("AddCallFunctionNode: Added '%s::%s' at (%d, %d)"),
        *FunctionClass->GetName(), *FunctionName.ToString(), NodePosX, NodePosY);

    return NewNode;
}

UEdGraphNode* UExGraphEditorLibrary::AddEventNode(
    UBlueprint* TargetBlueprint,
    UClass* EventSignatureClass,
    FName EventName,
    int32 NodePosX,
    int32 NodePosY)
{
    if (!TargetBlueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddEventNode: TargetBlueprint is null"));
        return nullptr;
    }

    if (!EventSignatureClass)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddEventNode: EventSignatureClass is null"));
        return nullptr;
    }

    UEdGraph* Graph = GetEventGraph(TargetBlueprint);
    if (!Graph)
    {
        return nullptr;
    }

    // Use FKismetEditorUtilities::AddDefaultEventNode for simpler event node creation
    // Note: NodePosY is passed by reference and will be updated
    int32 OutNodePosY = NodePosY;
    UK2Node_Event* EventNode = FKismetEditorUtilities::AddDefaultEventNode(
        TargetBlueprint,
        Graph,
        EventName,
        EventSignatureClass,
        OutNodePosY
    );

    if (EventNode)
    {
        // Set X position (AddDefaultEventNode doesn't take X position)
        EventNode->NodePosX = NodePosX;

        UE_LOG(LogExGraphEditor, Log, TEXT("AddEventNode: Added '%s::%s' at (%d, %d)"),
            *EventSignatureClass->GetName(), *EventName.ToString(), NodePosX, NodePosY);
    }
    else
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddEventNode: Failed to add '%s::%s'"),
            *EventSignatureClass->GetName(), *EventName.ToString());
    }

    return EventNode;
}

UEdGraphNode* UExGraphEditorLibrary::AddCustomEventNode(
    UBlueprint* TargetBlueprint,
    FName EventName,
    int32 NodePosX,
    int32 NodePosY)
{
    if (!TargetBlueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddCustomEventNode: TargetBlueprint is null"));
        return nullptr;
    }

    if (EventName.IsNone())
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddCustomEventNode: EventName is empty"));
        return nullptr;
    }

    UEdGraph* Graph = GetEventGraph(TargetBlueprint);
    if (!Graph)
    {
        return nullptr;
    }

    // Create custom event node
    UK2Node_CustomEvent* CustomEventNode = NewObject<UK2Node_CustomEvent>(Graph);
    CustomEventNode->CreateNewGuid();
    CustomEventNode->CustomFunctionName = EventName;
    CustomEventNode->NodePosX = NodePosX;
    CustomEventNode->NodePosY = NodePosY;

    // Add to graph and create pins
    Graph->AddNode(CustomEventNode, false, false);
    CustomEventNode->AllocateDefaultPins();

    // Notify changes
    Graph->NotifyGraphChanged();
    FBlueprintEditorUtils::MarkBlueprintAsModified(TargetBlueprint);

    UE_LOG(LogExGraphEditor, Log, TEXT("AddCustomEventNode: Added custom event '%s' at (%d, %d)"),
        *EventName.ToString(), NodePosX, NodePosY);

    return CustomEventNode;
}

UEdGraphNode* UExGraphEditorLibrary::AddBranchNode(
    UBlueprint* TargetBlueprint,
    int32 NodePosX,
    int32 NodePosY)
{
    if (!TargetBlueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddBranchNode: TargetBlueprint is null"));
        return nullptr;
    }

    UEdGraph* Graph = GetEventGraph(TargetBlueprint);
    if (!Graph)
    {
        return nullptr;
    }

    // Create the Branch (IfThenElse) node
    UK2Node_IfThenElse* NewNode = NewObject<UK2Node_IfThenElse>(Graph);
    NewNode->CreateNewGuid();
    NewNode->NodePosX = NodePosX;
    NewNode->NodePosY = NodePosY;

    // Add to graph and create pins
    Graph->AddNode(NewNode, false, false);
    NewNode->AllocateDefaultPins();

    // Notify changes
    Graph->NotifyGraphChanged();
    FBlueprintEditorUtils::MarkBlueprintAsModified(TargetBlueprint);

    UE_LOG(LogExGraphEditor, Log, TEXT("AddBranchNode: Added Branch node at (%d, %d)"), NodePosX, NodePosY);

    return NewNode;
}

UEdGraphNode* UExGraphEditorLibrary::AddVariableGetNode(
    UBlueprint* TargetBlueprint,
    FName VariableName,
    int32 NodePosX,
    int32 NodePosY)
{
    if (!TargetBlueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddVariableGetNode: TargetBlueprint is null"));
        return nullptr;
    }

    UEdGraph* Graph = GetEventGraph(TargetBlueprint);
    if (!Graph)
    {
        return nullptr;
    }

    // Verify the variable exists in the Blueprint
    FProperty* VarProperty = nullptr;
    for (FBPVariableDescription& Var : TargetBlueprint->NewVariables)
    {
        if (Var.VarName == VariableName)
        {
            VarProperty = TargetBlueprint->GeneratedClass ?
                TargetBlueprint->GeneratedClass->FindPropertyByName(VariableName) : nullptr;
            break;
        }
    }

    if (!VarProperty)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddVariableGetNode: Variable '%s' not found in Blueprint '%s'"),
            *VariableName.ToString(), *TargetBlueprint->GetName());
        return nullptr;
    }

    // Create the VariableGet node
    UK2Node_VariableGet* NewNode = NewObject<UK2Node_VariableGet>(Graph);
    NewNode->CreateNewGuid();
    NewNode->NodePosX = NodePosX;
    NewNode->NodePosY = NodePosY;

    // Set up the variable reference
    NewNode->VariableReference.SetSelfMember(VariableName);

    // Add to graph and create pins
    Graph->AddNode(NewNode, false, false);
    NewNode->AllocateDefaultPins();

    // Notify changes
    Graph->NotifyGraphChanged();
    FBlueprintEditorUtils::MarkBlueprintAsModified(TargetBlueprint);

    UE_LOG(LogExGraphEditor, Log, TEXT("AddVariableGetNode: Added getter for '%s' at (%d, %d)"),
        *VariableName.ToString(), NodePosX, NodePosY);

    return NewNode;
}

UEdGraphNode* UExGraphEditorLibrary::AddVariableSetNode(
    UBlueprint* TargetBlueprint,
    FName VariableName,
    int32 NodePosX,
    int32 NodePosY)
{
    if (!TargetBlueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddVariableSetNode: TargetBlueprint is null"));
        return nullptr;
    }

    UEdGraph* Graph = GetEventGraph(TargetBlueprint);
    if (!Graph)
    {
        return nullptr;
    }

    // Verify the variable exists in the Blueprint
    FProperty* VarProperty = nullptr;
    for (FBPVariableDescription& Var : TargetBlueprint->NewVariables)
    {
        if (Var.VarName == VariableName)
        {
            VarProperty = TargetBlueprint->GeneratedClass ?
                TargetBlueprint->GeneratedClass->FindPropertyByName(VariableName) : nullptr;
            break;
        }
    }

    if (!VarProperty)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddVariableSetNode: Variable '%s' not found in Blueprint '%s'"),
            *VariableName.ToString(), *TargetBlueprint->GetName());
        return nullptr;
    }

    // Create the VariableSet node
    UK2Node_VariableSet* NewNode = NewObject<UK2Node_VariableSet>(Graph);
    NewNode->CreateNewGuid();
    NewNode->NodePosX = NodePosX;
    NewNode->NodePosY = NodePosY;

    // Set up the variable reference
    NewNode->VariableReference.SetSelfMember(VariableName);

    // Add to graph and create pins
    Graph->AddNode(NewNode, false, false);
    NewNode->AllocateDefaultPins();

    // Notify changes
    Graph->NotifyGraphChanged();
    FBlueprintEditorUtils::MarkBlueprintAsModified(TargetBlueprint);

    UE_LOG(LogExGraphEditor, Log, TEXT("AddVariableSetNode: Added setter for '%s' at (%d, %d)"),
        *VariableName.ToString(), NodePosX, NodePosY);

    return NewNode;
}

UEdGraphNode* UExGraphEditorLibrary::AddFunctionNodeByName(
    UBlueprint* TargetBlueprint,
    const FString& FunctionName,
    UClass* OwnerClass,
    int32 NodePosX,
    int32 NodePosY)
{
    if (!TargetBlueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddFunctionNodeByName: TargetBlueprint is null"));
        return nullptr;
    }

    if (FunctionName.IsEmpty())
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddFunctionNodeByName: FunctionName is empty"));
        return nullptr;
    }

    FName FuncName(*FunctionName);
    UFunction* FoundFunction = nullptr;
    UClass* FoundClass = nullptr;

    // If OwnerClass is provided, search only in that class (supports ANY class's member methods)
    if (OwnerClass)
    {
        FoundFunction = OwnerClass->FindFunctionByName(FuncName);
        if (FoundFunction)
        {
            FoundClass = OwnerClass;
        }
        else
        {
            UE_LOG(LogExGraphEditor, Warning, TEXT("AddFunctionNodeByName: Function '%s' not found in class '%s'"),
                *FunctionName, *OwnerClass->GetName());
            return nullptr;
        }
    }
    else
    {
        // No OwnerClass provided - search common library classes (backward compatibility)
        TArray<UClass*> LibraryClasses = {
            UKismetSystemLibrary::StaticClass(),
            UGameplayStatics::StaticClass(),
            UKismetMathLibrary::StaticClass(),
            UKismetStringLibrary::StaticClass(),
            UKismetArrayLibrary::StaticClass(),
            UKismetTextLibrary::StaticClass(),
            AActor::StaticClass(),
            UActorComponent::StaticClass(),
        };

        for (UClass* LibClass : LibraryClasses)
        {
            UFunction* Func = LibClass->FindFunctionByName(FuncName);
            if (Func)
            {
                FoundFunction = Func;
                FoundClass = LibClass;
                break;
            }
        }

        if (!FoundFunction)
        {
            UE_LOG(LogExGraphEditor, Warning, TEXT("AddFunctionNodeByName: Function '%s' not found in any common library class"), *FunctionName);
            return nullptr;
        }
    }

    UEdGraph* Graph = GetEventGraph(TargetBlueprint);
    if (!Graph)
    {
        return nullptr;
    }

    // Create the node
    UK2Node_CallFunction* NewNode = NewObject<UK2Node_CallFunction>(Graph);
    NewNode->CreateNewGuid();
    NewNode->NodePosX = NodePosX;
    NewNode->NodePosY = NodePosY;

    // Set up the function reference
    // SetFromFunction() automatically handles member vs static functions
    // and will create a Target/self pin for member methods
    NewNode->SetFromFunction(FoundFunction);

    // Add to graph and create pins
    Graph->AddNode(NewNode, false, false);
    NewNode->AllocateDefaultPins();

    // Notify changes
    Graph->NotifyGraphChanged();
    FBlueprintEditorUtils::MarkBlueprintAsModified(TargetBlueprint);

    UE_LOG(LogExGraphEditor, Log, TEXT("AddFunctionNodeByName: Added '%s::%s' at (%d, %d)"),
        *FoundClass->GetName(), *FunctionName, NodePosX, NodePosY);

    return NewNode;
}

// ============================================================================
// UPDATE Operations
// ============================================================================

bool UExGraphEditorLibrary::ConnectNodes(
    UEdGraphNode* NodeA,
    const FString& PinNameA,
    UEdGraphNode* NodeB,
    const FString& PinNameB)
{
    if (!NodeA || !NodeB)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("ConnectNodes: One or both nodes are null"));
        return false;
    }

    UEdGraphPin* PinA = FindPinByName(NodeA, PinNameA);
    UEdGraphPin* PinB = FindPinByName(NodeB, PinNameB);

    if (!PinA)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("ConnectNodes: Pin '%s' not found on NodeA"), *PinNameA);
        return false;
    }

    if (!PinB)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("ConnectNodes: Pin '%s' not found on NodeB"), *PinNameB);
        return false;
    }

    // Use the schema to validate and create the connection
    const UEdGraphSchema* Schema = NodeA->GetSchema();
    if (!Schema)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("ConnectNodes: Could not get graph schema"));
        return false;
    }

    bool bSuccess = Schema->TryCreateConnection(PinA, PinB);
    if (bSuccess)
    {
        // Refresh Blueprint editor
        if (UEdGraph* Graph = NodeA->GetGraph())
        {
            Graph->NotifyGraphChanged();
            if (UBlueprint* Blueprint = FBlueprintEditorUtils::FindBlueprintForGraph(Graph))
            {
                FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
            }
        }

        UE_LOG(LogExGraphEditor, Log, TEXT("ConnectNodes: Connected '%s' -> '%s'"),
            *PinA->PinName.ToString(), *PinB->PinName.ToString());
    }
    else
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("ConnectNodes: Failed to connect '%s' -> '%s'"),
            *PinA->PinName.ToString(), *PinB->PinName.ToString());
    }

    return bSuccess;
}

bool UExGraphEditorLibrary::SetPinDefaultValue(
    UEdGraphNode* Node,
    const FString& PinName,
    const FString& NewValue)
{
    if (!Node)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("SetPinDefaultValue: Node is null"));
        return false;
    }

    UEdGraphPin* Pin = FindPinByName(Node, PinName);
    if (!Pin)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("SetPinDefaultValue: Pin '%s' not found"), *PinName);
        return false;
    }

    const UEdGraphSchema_K2* K2Schema = GetDefault<UEdGraphSchema_K2>();
    K2Schema->TrySetDefaultValue(*Pin, NewValue);

    // Refresh Blueprint editor
    if (UEdGraph* Graph = Node->GetGraph())
    {
        Graph->NotifyGraphChanged();
        if (UBlueprint* Blueprint = FBlueprintEditorUtils::FindBlueprintForGraph(Graph))
        {
            FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
        }
    }

    UE_LOG(LogExGraphEditor, Log, TEXT("SetPinDefaultValue: Set '%s' = '%s'"),
        *Pin->PinName.ToString(), *NewValue);

    return true;
}

// For Blueprint compilation, use BlueprintEditorLibrary.compile_blueprint()

// ============================================================================
// READ Operations (Graph Node Queries)
// ============================================================================

TArray<UEdGraphNode*> UExGraphEditorLibrary::GetAllNodes(UBlueprint* Blueprint)
{
    TArray<UEdGraphNode*> Result;

    if (!Blueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("GetAllNodes: Blueprint is null"));
        return Result;
    }

    UEdGraph* Graph = GetEventGraph(Blueprint);
    if (!Graph)
    {
        return Result;
    }

    Result = Graph->Nodes;
    UE_LOG(LogExGraphEditor, Log, TEXT("GetAllNodes: Found %d nodes in '%s'"), Result.Num(), *Blueprint->GetName());

    return Result;
}

TArray<FString> UExGraphEditorLibrary::GetNodePinNames(UEdGraphNode* Node)
{
    TArray<FString> Result;

    if (!Node)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("GetNodePinNames: Node is null"));
        return Result;
    }

    for (UEdGraphPin* Pin : Node->Pins)
    {
        FString Direction = (Pin->Direction == EGPD_Input) ? TEXT("In") : TEXT("Out");
        FString PinInfo = FString::Printf(TEXT("%s:%s"), *Direction, *Pin->PinName.ToString());
        Result.Add(PinInfo);
    }

    return Result;
}

FString UExGraphEditorLibrary::GetNodeTitle(UEdGraphNode* Node)
{
    if (!Node)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("GetNodeTitle: Node is null"));
        return TEXT("");
    }

    return Node->GetNodeTitle(ENodeTitleType::FullTitle).ToString();
}

// For Blueprint variables, use BlueprintEditorLibrary.add_member_variable()

// ============================================================================
// DELETE Operations
// ============================================================================

bool UExGraphEditorLibrary::DeleteNode(UBlueprint* Blueprint, UEdGraphNode* Node)
{
    if (!Blueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("DeleteNode: Blueprint is null"));
        return false;
    }

    if (!Node)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("DeleteNode: Node is null"));
        return false;
    }

    UEdGraph* Graph = Node->GetGraph();
    if (!Graph)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("DeleteNode: Node has no graph"));
        return false;
    }

    FString NodeTitle = Node->GetNodeTitle(ENodeTitleType::FullTitle).ToString();

    // Use FBlueprintEditorUtils for safe removal (handles pin cleanup)
    FBlueprintEditorUtils::RemoveNode(Blueprint, Node, true);

    Graph->NotifyGraphChanged();
    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

    UE_LOG(LogExGraphEditor, Log, TEXT("DeleteNode: Removed '%s'"), *NodeTitle);

    return true;
}

bool UExGraphEditorLibrary::DisconnectPin(UEdGraphNode* Node, const FString& PinName)
{
    if (!Node)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("DisconnectPin: Node is null"));
        return false;
    }

    UEdGraphPin* Pin = FindPinByName(Node, PinName);
    if (!Pin)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("DisconnectPin: Pin '%s' not found"), *PinName);
        return false;
    }

    int32 NumLinks = Pin->LinkedTo.Num();
    Pin->BreakAllPinLinks();

    if (UEdGraph* Graph = Node->GetGraph())
    {
        Graph->NotifyGraphChanged();
        if (UBlueprint* Blueprint = FBlueprintEditorUtils::FindBlueprintForGraph(Graph))
        {
            FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
        }
    }

    UE_LOG(LogExGraphEditor, Log, TEXT("DisconnectPin: Broke %d links from '%s'"), NumLinks, *Pin->PinName.ToString());

    return true;
}
