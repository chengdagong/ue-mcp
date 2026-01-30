#include "ExGraphEditorLibrary.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "AssetToolsModule.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_CallFunction.h"
#include "K2Node_Event.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "Factories/BlueprintFactory.h"

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
// CREATE Operations
// ============================================================================

UBlueprint* UExGraphEditorLibrary::CreateBlueprintAsset(
    const FString& AssetPath,
    const FString& AssetName,
    UClass* ParentClass)
{
    if (AssetPath.IsEmpty() || AssetName.IsEmpty())
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("CreateBlueprintAsset: AssetPath or AssetName is empty"));
        return nullptr;
    }

    IAssetTools& AssetTools = FModuleManager::GetModuleChecked<FAssetToolsModule>("AssetTools").Get();
    UBlueprintFactory* Factory = NewObject<UBlueprintFactory>();

    // Default to AActor if no parent class specified
    if (ParentClass == nullptr)
    {
        ParentClass = AActor::StaticClass();
    }

    Factory->ParentClass = ParentClass;

    UObject* NewAsset = AssetTools.CreateAsset(AssetName, AssetPath, UBlueprint::StaticClass(), Factory);

    UBlueprint* NewBP = Cast<UBlueprint>(NewAsset);
    if (NewBP)
    {
        UE_LOG(LogExGraphEditor, Log, TEXT("CreateBlueprintAsset: Created '%s/%s' with parent '%s'"),
            *AssetPath, *AssetName, *ParentClass->GetName());
        FBlueprintEditorUtils::MarkBlueprintAsModified(NewBP);
    }
    else
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("CreateBlueprintAsset: Failed to create Blueprint at '%s/%s'"),
            *AssetPath, *AssetName);
    }

    return NewBP;
}

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

    // Create the event node
    UK2Node_Event* EventNode = NewObject<UK2Node_Event>(Graph);
    EventNode->CreateNewGuid();
    EventNode->EventReference.SetExternalMember(EventName, EventSignatureClass);
    EventNode->NodePosX = NodePosX;
    EventNode->NodePosY = NodePosY;

    // Add to graph and create pins
    Graph->AddNode(EventNode, false, false);
    EventNode->AllocateDefaultPins();

    // Notify changes
    Graph->NotifyGraphChanged();
    FBlueprintEditorUtils::MarkBlueprintAsModified(TargetBlueprint);

    UE_LOG(LogExGraphEditor, Log, TEXT("AddEventNode: Added '%s::%s' at (%d, %d)"),
        *EventSignatureClass->GetName(), *EventName.ToString(), NodePosX, NodePosY);

    return EventNode;
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

    UE_LOG(LogExGraphEditor, Log, TEXT("SetPinDefaultValue: Set '%s' = '%s'"),
        *Pin->PinName.ToString(), *NewValue);

    return true;
}

bool UExGraphEditorLibrary::CompileBlueprint(UBlueprint* Blueprint)
{
    if (!Blueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("CompileBlueprint: Blueprint is null"));
        return false;
    }

    FKismetEditorUtilities::CompileBlueprint(Blueprint);

    // Check for compilation errors
    bool bHasErrors = (Blueprint->Status == BS_Error);
    if (bHasErrors)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("CompileBlueprint: '%s' compiled with errors"), *Blueprint->GetName());
    }
    else
    {
        UE_LOG(LogExGraphEditor, Log, TEXT("CompileBlueprint: '%s' compiled successfully"), *Blueprint->GetName());
    }

    return !bHasErrors;
}

// ============================================================================
// READ Operations
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

TArray<FName> UExGraphEditorLibrary::GetBlueprintVariables(UBlueprint* Blueprint)
{
    TArray<FName> Result;

    if (!Blueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("GetBlueprintVariables: Blueprint is null"));
        return Result;
    }

    // Get variables from the Blueprint's NewVariables array
    for (const FBPVariableDescription& Var : Blueprint->NewVariables)
    {
        Result.Add(Var.VarName);
    }

    UE_LOG(LogExGraphEditor, Log, TEXT("GetBlueprintVariables: Found %d variables in '%s'"),
        Result.Num(), *Blueprint->GetName());

    return Result;
}

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
    }

    UE_LOG(LogExGraphEditor, Log, TEXT("DisconnectPin: Broke %d links from '%s'"), NumLinks, *Pin->PinName.ToString());

    return true;
}

bool UExGraphEditorLibrary::AddMemberVariable(
    UBlueprint* Blueprint,
    FName VariableName,
    const FString& VariableType)
{
    if (!Blueprint)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddMemberVariable: Blueprint is null"));
        return false;
    }

    if (VariableName == NAME_None)
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddMemberVariable: VariableName is empty"));
        return false;
    }

    // Check if variable already exists
    for (const FBPVariableDescription& Var : Blueprint->NewVariables)
    {
        if (Var.VarName == VariableName)
        {
            UE_LOG(LogExGraphEditor, Warning, TEXT("AddMemberVariable: Variable '%s' already exists in Blueprint '%s'"),
                *VariableName.ToString(), *Blueprint->GetName());
            return false;
        }
    }

    // Determine the pin type based on VariableType string
    FEdGraphPinType PinType;
    FString TypeLower = VariableType.ToLower();

    if (TypeLower == TEXT("bool") || TypeLower == TEXT("boolean"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Boolean;
    }
    else if (TypeLower == TEXT("int") || TypeLower == TEXT("int32") || TypeLower == TEXT("integer"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Int;
    }
    else if (TypeLower == TEXT("int64"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Int64;
    }
    else if (TypeLower == TEXT("float") || TypeLower == TEXT("real"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Real;
        PinType.PinSubCategory = UEdGraphSchema_K2::PC_Float;
    }
    else if (TypeLower == TEXT("double"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Real;
        PinType.PinSubCategory = UEdGraphSchema_K2::PC_Double;
    }
    else if (TypeLower == TEXT("string") || TypeLower == TEXT("fstring"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_String;
    }
    else if (TypeLower == TEXT("name") || TypeLower == TEXT("fname"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Name;
    }
    else if (TypeLower == TEXT("text") || TypeLower == TEXT("ftext"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Text;
    }
    else if (TypeLower == TEXT("vector") || TypeLower == TEXT("fvector"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
        PinType.PinSubCategoryObject = TBaseStructure<FVector>::Get();
    }
    else if (TypeLower == TEXT("rotator") || TypeLower == TEXT("frotator"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
        PinType.PinSubCategoryObject = TBaseStructure<FRotator>::Get();
    }
    else if (TypeLower == TEXT("transform") || TypeLower == TEXT("ftransform"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
        PinType.PinSubCategoryObject = TBaseStructure<FTransform>::Get();
    }
    else if (TypeLower == TEXT("vector2d") || TypeLower == TEXT("fvector2d"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
        PinType.PinSubCategoryObject = TBaseStructure<FVector2D>::Get();
    }
    else if (TypeLower == TEXT("linearcolor") || TypeLower == TEXT("flinearcolor") || TypeLower == TEXT("color"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
        PinType.PinSubCategoryObject = TBaseStructure<FLinearColor>::Get();
    }
    else
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddMemberVariable: Unknown type '%s'. Supported types: bool, int, int64, float, double, string, name, text, vector, rotator, transform, vector2d, color"),
            *VariableType);
        return false;
    }

    // Add the variable using FBlueprintEditorUtils
    bool bSuccess = FBlueprintEditorUtils::AddMemberVariable(Blueprint, VariableName, PinType);

    if (bSuccess)
    {
        FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
        UE_LOG(LogExGraphEditor, Log, TEXT("AddMemberVariable: Added '%s' (%s) to Blueprint '%s'"),
            *VariableName.ToString(), *VariableType, *Blueprint->GetName());
    }
    else
    {
        UE_LOG(LogExGraphEditor, Warning, TEXT("AddMemberVariable: Failed to add '%s' to Blueprint '%s'"),
            *VariableName.ToString(), *Blueprint->GetName());
    }

    return bSuccess;
}
