// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "ExSlateTabLibrary.generated.h"

class UBlueprint;
class UObject;

/**
 * Python/Blueprint utility library for manipulating Slate UI tabs
 * Provides functionality to switch between tabs in asset editors like Blueprint Editor
 *
 * Common Blueprint Editor Tab IDs:
 * - "Inspector" (Details panel)
 * - "SCSViewport" (Viewport/Components view)
 * - "GraphEditor" (Event Graph and other graphs)
 * - "MyBlueprint" (My Blueprint panel)
 * - "PaletteList" (Palette)
 * - "CompilerResults" (Compiler Results)
 * - "FindResults" (Find Results)
 * - "ConstructionScriptEditor" (Construction Script)
 * - "Debug" (Debug panel)
 * - "BookmarkList" (Bookmarks)
 */
UCLASS()
class EXTRAPYTHONAPIS_API UExSlateTabLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Invoke (open/focus) a tab in the Blueprint Editor for the given Blueprint asset
	 *
	 * @param Blueprint The Blueprint asset whose editor tab should be invoked
	 * @param TabId The tab identifier (e.g., "SCSViewport", "GraphEditor", "Inspector")
	 * @return True if the tab was successfully invoked
	 */
	UFUNCTION(BlueprintCallable, Category = "Python|SlateTab", meta = (DevelopmentOnly))
	static bool InvokeBlueprintEditorTab(UBlueprint* Blueprint, FName TabId);

	/**
	 * Invoke (open/focus) a tab in the asset editor for any given asset
	 *
	 * @param Asset The asset whose editor tab should be invoked
	 * @param TabId The tab identifier
	 * @return True if the tab was successfully invoked
	 */
	UFUNCTION(BlueprintCallable, Category = "Python|SlateTab", meta = (DevelopmentOnly))
	static bool InvokeAssetEditorTab(UObject* Asset, FName TabId);

	/**
	 * Get a list of available tab IDs for the Blueprint Editor
	 *
	 * @return Array of available tab ID names
	 */
	UFUNCTION(BlueprintPure, Category = "Python|SlateTab", meta = (DevelopmentOnly))
	static TArray<FName> GetBlueprintEditorTabIds();

	/**
	 * Switch the Blueprint Editor to Components/Viewport mode
	 * This focuses on the SCS Viewport tab showing the component hierarchy
	 *
	 * @param Blueprint The Blueprint asset
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "Python|SlateTab", meta = (DevelopmentOnly))
	static bool SwitchToViewportMode(UBlueprint* Blueprint);

	/**
	 * Switch the Blueprint Editor to Graph mode (Event Graph)
	 * This focuses on the Graph Editor tab
	 *
	 * @param Blueprint The Blueprint asset
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "Python|SlateTab", meta = (DevelopmentOnly))
	static bool SwitchToGraphMode(UBlueprint* Blueprint);

	/**
	 * Focus the Details/Inspector panel in the Blueprint Editor
	 *
	 * @param Blueprint The Blueprint asset
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "Python|SlateTab", meta = (DevelopmentOnly))
	static bool FocusDetailsPanel(UBlueprint* Blueprint);

	/**
	 * Focus the My Blueprint panel in the Blueprint Editor
	 *
	 * @param Blueprint The Blueprint asset
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "Python|SlateTab", meta = (DevelopmentOnly))
	static bool FocusMyBlueprintPanel(UBlueprint* Blueprint);

	/**
	 * Open the Construction Script editor tab in the Blueprint Editor
	 *
	 * @param Blueprint The Blueprint asset
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "Python|SlateTab", meta = (DevelopmentOnly))
	static bool OpenConstructionScript(UBlueprint* Blueprint);

	/**
	 * Open the Compiler Results panel in the Blueprint Editor
	 *
	 * @param Blueprint The Blueprint asset
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "Python|SlateTab", meta = (DevelopmentOnly))
	static bool OpenCompilerResults(UBlueprint* Blueprint);

	/**
	 * Check if an asset editor is currently open for the given asset
	 *
	 * @param Asset The asset to check
	 * @return True if an editor is open for this asset
	 */
	UFUNCTION(BlueprintPure, Category = "Python|SlateTab", meta = (DevelopmentOnly))
	static bool IsAssetEditorOpen(UObject* Asset);

	/**
	 * Focus (bring to front) the asset editor window for the given asset
	 *
	 * @param Asset The asset whose editor window should be focused
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "Python|SlateTab", meta = (DevelopmentOnly))
	static bool FocusAssetEditorWindow(UObject* Asset);
};
