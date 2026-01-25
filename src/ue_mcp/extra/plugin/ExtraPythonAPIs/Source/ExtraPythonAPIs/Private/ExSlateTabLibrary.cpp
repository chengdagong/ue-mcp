// Copyright Epic Games, Inc. All Rights Reserved.

#include "ExSlateTabLibrary.h"
#include "Engine/Blueprint.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "Editor.h"
#include "BlueprintEditorTabs.h"
#include "Framework/Docking/TabManager.h"
#include "Framework/Application/SlateApplication.h"

DEFINE_LOG_CATEGORY_STATIC(LogExSlateTab, Log, All);

bool UExSlateTabLibrary::InvokeBlueprintEditorTab(UBlueprint* Blueprint, FName TabId)
{
	if (!Blueprint)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("InvokeBlueprintEditorTab: Blueprint is null"));
		return false;
	}

	return InvokeAssetEditorTab(Blueprint, TabId);
}

bool UExSlateTabLibrary::InvokeAssetEditorTab(UObject* Asset, FName TabId)
{
	if (!Asset)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("InvokeAssetEditorTab: Asset is null"));
		return false;
	}

	if (!GEditor)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("InvokeAssetEditorTab: GEditor is null"));
		return false;
	}

	UAssetEditorSubsystem* AssetEditorSubsystem = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
	if (!AssetEditorSubsystem)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("InvokeAssetEditorTab: AssetEditorSubsystem is null"));
		return false;
	}

	IAssetEditorInstance* EditorInstance = AssetEditorSubsystem->FindEditorForAsset(Asset, false);
	if (!EditorInstance)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("InvokeAssetEditorTab: No editor found for asset '%s'"), *Asset->GetName());
		return false;
	}

	// Get the tab manager from the editor instance
	TSharedPtr<FTabManager> TabManager = EditorInstance->GetAssociatedTabManager();
	if (!TabManager.IsValid())
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("InvokeAssetEditorTab: TabManager is invalid"));
		return false;
	}

	// Try to invoke the tab
	TSharedPtr<SDockTab> Tab = TabManager->TryInvokeTab(TabId);
	if (Tab.IsValid())
	{
		UE_LOG(LogExSlateTab, Log, TEXT("InvokeAssetEditorTab: Successfully invoked tab '%s' for asset '%s'"),
			*TabId.ToString(), *Asset->GetName());
		return true;
	}

	UE_LOG(LogExSlateTab, Warning, TEXT("InvokeAssetEditorTab: Failed to invoke tab '%s' for asset '%s'"),
		*TabId.ToString(), *Asset->GetName());
	return false;
}

TArray<FName> UExSlateTabLibrary::GetBlueprintEditorTabIds()
{
	TArray<FName> TabIds;

	// Add all known Blueprint Editor tab IDs
	TabIds.Add(FBlueprintEditorTabs::DetailsID);           // "Inspector"
	TabIds.Add(FBlueprintEditorTabs::SCSViewportID);       // "SCSViewport"
	TabIds.Add(FBlueprintEditorTabs::GraphEditorID);       // "GraphEditor"
	TabIds.Add(FBlueprintEditorTabs::MyBlueprintID);       // "MyBlueprint"
	TabIds.Add(FBlueprintEditorTabs::PaletteID);           // "PaletteList"
	TabIds.Add(FBlueprintEditorTabs::CompilerResultsID);   // "CompilerResults"
	TabIds.Add(FBlueprintEditorTabs::FindResultsID);       // "FindResults"
	TabIds.Add(FBlueprintEditorTabs::ConstructionScriptEditorID); // "ConstructionScriptEditor"
	TabIds.Add(FBlueprintEditorTabs::DebugID);             // "Debug"
	TabIds.Add(FBlueprintEditorTabs::BookmarksID);         // "BookmarkList"
	TabIds.Add(FBlueprintEditorTabs::DefaultEditorID);     // "DefaultEditor"
	TabIds.Add(FBlueprintEditorTabs::TimelineEditorID);    // "TimelineEditor"

	return TabIds;
}

bool UExSlateTabLibrary::SwitchToViewportMode(UBlueprint* Blueprint)
{
	return InvokeBlueprintEditorTab(Blueprint, FBlueprintEditorTabs::SCSViewportID);
}

bool UExSlateTabLibrary::SwitchToGraphMode(UBlueprint* Blueprint)
{
	return InvokeBlueprintEditorTab(Blueprint, FBlueprintEditorTabs::GraphEditorID);
}

bool UExSlateTabLibrary::FocusDetailsPanel(UBlueprint* Blueprint)
{
	return InvokeBlueprintEditorTab(Blueprint, FBlueprintEditorTabs::DetailsID);
}

bool UExSlateTabLibrary::FocusMyBlueprintPanel(UBlueprint* Blueprint)
{
	return InvokeBlueprintEditorTab(Blueprint, FBlueprintEditorTabs::MyBlueprintID);
}

bool UExSlateTabLibrary::OpenConstructionScript(UBlueprint* Blueprint)
{
	return InvokeBlueprintEditorTab(Blueprint, FBlueprintEditorTabs::ConstructionScriptEditorID);
}

bool UExSlateTabLibrary::OpenCompilerResults(UBlueprint* Blueprint)
{
	return InvokeBlueprintEditorTab(Blueprint, FBlueprintEditorTabs::CompilerResultsID);
}

bool UExSlateTabLibrary::IsAssetEditorOpen(UObject* Asset)
{
	if (!Asset || !GEditor)
	{
		return false;
	}

	UAssetEditorSubsystem* AssetEditorSubsystem = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
	if (!AssetEditorSubsystem)
	{
		return false;
	}

	IAssetEditorInstance* EditorInstance = AssetEditorSubsystem->FindEditorForAsset(Asset, false);
	return EditorInstance != nullptr;
}

bool UExSlateTabLibrary::FocusAssetEditorWindow(UObject* Asset)
{
	if (!Asset)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("FocusAssetEditorWindow: Asset is null"));
		return false;
	}

	if (!GEditor)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("FocusAssetEditorWindow: GEditor is null"));
		return false;
	}

	UAssetEditorSubsystem* AssetEditorSubsystem = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
	if (!AssetEditorSubsystem)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("FocusAssetEditorWindow: AssetEditorSubsystem is null"));
		return false;
	}

	IAssetEditorInstance* EditorInstance = AssetEditorSubsystem->FindEditorForAsset(Asset, true); // true = focus if open
	if (EditorInstance)
	{
		EditorInstance->FocusWindow(Asset);
		UE_LOG(LogExSlateTab, Log, TEXT("FocusAssetEditorWindow: Focused editor for asset '%s'"), *Asset->GetName());
		return true;
	}

	UE_LOG(LogExSlateTab, Warning, TEXT("FocusAssetEditorWindow: No editor found for asset '%s'"), *Asset->GetName());
	return false;
}

bool UExSlateTabLibrary::OpenOutputLog()
{
	return InvokeGlobalTab(FName("OutputLog"));
}

bool UExSlateTabLibrary::InvokeGlobalTab(FName TabId)
{
	TSharedPtr<FGlobalTabmanager> GlobalTabManager = FGlobalTabmanager::Get();
	if (!GlobalTabManager.IsValid())
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("InvokeGlobalTab: FGlobalTabmanager is invalid"));
		return false;
	}

	TSharedPtr<SDockTab> Tab = GlobalTabManager->TryInvokeTab(TabId);
	if (Tab.IsValid())
	{
		UE_LOG(LogExSlateTab, Log, TEXT("InvokeGlobalTab: Successfully invoked global tab '%s'"), *TabId.ToString());

		// Process Slate tick to ensure UI updates
		if (FSlateApplication::IsInitialized())
		{
			FSlateApplication::Get().Tick();
		}

		return true;
	}

	UE_LOG(LogExSlateTab, Warning, TEXT("InvokeGlobalTab: Failed to invoke global tab '%s'"), *TabId.ToString());
	return false;
}
