// Copyright Epic Games, Inc. All Rights Reserved.

#include "ExSlateTabLibrary.h"
#include "Engine/Blueprint.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "Editor.h"
#include "BlueprintEditorTabs.h"
#include "BlueprintEditor.h"
#include "BlueprintEditorModes.h"
#include "Framework/Docking/TabManager.h"
#include "Framework/Application/SlateApplication.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "EdGraph/EdGraph.h"

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
	if (!Blueprint)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("SwitchToViewportMode: Blueprint is null"));
		return false;
	}

	if (!GEditor)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("SwitchToViewportMode: GEditor is null"));
		return false;
	}

	UAssetEditorSubsystem* AssetEditorSubsystem = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
	if (!AssetEditorSubsystem)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("SwitchToViewportMode: AssetEditorSubsystem is null"));
		return false;
	}

	IAssetEditorInstance* EditorInstance = AssetEditorSubsystem->FindEditorForAsset(Blueprint, false);
	if (!EditorInstance)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("SwitchToViewportMode: No editor found for Blueprint '%s'"), *Blueprint->GetName());
		return false;
	}

	// Cast to FBlueprintEditor to access SetCurrentMode
	FBlueprintEditor* BlueprintEditor = static_cast<FBlueprintEditor*>(EditorInstance);
	if (!BlueprintEditor)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("SwitchToViewportMode: Failed to cast to FBlueprintEditor"));
		return false;
	}

	// Switch to Components mode
	BlueprintEditor->SetCurrentMode(FBlueprintEditorApplicationModes::BlueprintComponentsMode);

	// Also invoke the SCSViewport tab to ensure UI updates
	InvokeBlueprintEditorTab(Blueprint, FBlueprintEditorTabs::SCSViewportID);

	UE_LOG(LogExSlateTab, Log, TEXT("SwitchToViewportMode: Switched to Components mode for Blueprint '%s'"), *Blueprint->GetName());
	return true;
}

bool UExSlateTabLibrary::SwitchToGraphMode(UBlueprint* Blueprint)
{
	if (!Blueprint)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("SwitchToGraphMode: Blueprint is null"));
		return false;
	}

	// Find the EventGraph in UbergraphPages
	UEdGraph* TargetGraph = nullptr;
	for (UEdGraph* Graph : Blueprint->UbergraphPages)
	{
		if (Graph && Graph->GetName() == TEXT("EventGraph"))
		{
			TargetGraph = Graph;
			break;
		}
	}

	// If no EventGraph found, try the first UbergraphPage
	if (!TargetGraph && Blueprint->UbergraphPages.Num() > 0)
	{
		TargetGraph = Blueprint->UbergraphPages[0];
	}

	if (!TargetGraph)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("SwitchToGraphMode: No EventGraph found for Blueprint '%s'"), *Blueprint->GetName());
		return false;
	}

	// Use FKismetEditorUtilities to open and focus on the graph
	FKismetEditorUtilities::BringKismetToFocusAttentionOnObject(TargetGraph);

	UE_LOG(LogExSlateTab, Log, TEXT("SwitchToGraphMode: Switched to Graph mode for Blueprint '%s' (Graph: %s)"),
		*Blueprint->GetName(), *TargetGraph->GetName());
	return true;
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

bool UExSlateTabLibrary::CloseOutputLog()
{
	return CloseGlobalTab(FName("OutputLog"));
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

bool UExSlateTabLibrary::CloseGlobalTab(FName TabId)
{
	TSharedPtr<FGlobalTabmanager> GlobalTabManager = FGlobalTabmanager::Get();
	if (!GlobalTabManager.IsValid())
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("CloseGlobalTab: FGlobalTabmanager is invalid"));
		return false;
	}

	TSharedPtr<SDockTab> Tab = GlobalTabManager->FindExistingLiveTab(TabId);
	if (Tab.IsValid())
	{
		Tab->RequestCloseTab();
		UE_LOG(LogExSlateTab, Log, TEXT("CloseGlobalTab: Successfully requested close for global tab '%s'"), *TabId.ToString());

		// Process Slate tick to ensure UI updates
		if (FSlateApplication::IsInitialized())
		{
			FSlateApplication::Get().Tick();
		}

		return true;
	}

	UE_LOG(LogExSlateTab, Warning, TEXT("CloseGlobalTab: Global tab '%s' not found or not open"), *TabId.ToString());
	return false;
}

bool UExSlateTabLibrary::RefreshSlateView()
{
	UE_LOG(LogExSlateTab, Log, TEXT("RefreshSlateView: Refreshing Slate UI via Output Log toggle"));

	// Open the Output Log to trigger UI processing
	bool bOpened = OpenOutputLog();
	if (!bOpened)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("RefreshSlateView: Failed to open Output Log"));
		return false;
	}

	// Close the Output Log
	bool bClosed = CloseOutputLog();
	if (!bClosed)
	{
		UE_LOG(LogExSlateTab, Warning, TEXT("RefreshSlateView: Failed to close Output Log"));
		return false;
	}

	UE_LOG(LogExSlateTab, Log, TEXT("RefreshSlateView: Successfully refreshed Slate UI"));
	return true;
}
