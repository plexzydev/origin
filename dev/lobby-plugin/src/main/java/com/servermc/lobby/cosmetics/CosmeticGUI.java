package com.servermc.lobby.cosmetics;

import com.servermc.lobby.LobbyCore;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.Material;
import org.bukkit.Sound;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;

import java.util.ArrayList;
import java.util.List;

/**
 * CosmeticGUI - Beautiful inventory-based cosmetic selector.
 */
public class CosmeticGUI implements Listener {

    private final LobbyCore plugin;

    private static final TextColor RED = TextColor.color(255, 60, 40);
    private static final TextColor ORANGE = TextColor.color(255, 140, 0);
    private static final TextColor YELLOW = TextColor.color(255, 220, 50);
    private static final TextColor GREEN = TextColor.color(85, 255, 85);
    private static final TextColor GRAY = TextColor.color(150, 150, 150);
    private static final TextColor WHITE = TextColor.color(255, 255, 255);
    private static final TextColor GOLD = TextColor.color(255, 200, 50);
    private static final TextColor DARK_GRAY = TextColor.color(85, 85, 85);
    private static final TextColor AQUA = TextColor.color(85, 255, 255);

    private static final String MAIN_MENU_TITLE = "§c§l🔥 §6§lCosméticos §c§l🔥";
    private static final String PARTICLES_TITLE = "§6§l✦ Partículas ✦";
    private static final String PETS_TITLE = "§a§l✦ Mascotas ✦";
    private static final String ARMOR_TITLE = "§d§l✦ Armaduras ✦";

    public CosmeticGUI(LobbyCore plugin) {
        this.plugin = plugin;
    }

    // ═══ Open Main Menu ═══
    public void openMainMenu(Player player) {
        Inventory inv = Bukkit.createInventory(null, 54, MAIN_MENU_TITLE);

        // Fill background with dark glass
        ItemStack bg = createItem(Material.BLACK_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 54; i++) inv.setItem(i, bg);

        // Particles category
        ItemStack particles = createItem(Material.BLAZE_POWDER, "§6§l✦ Partículas",
                "§7Anillos, halos, alas y auras",
                "§7de partículas que te rodean.",
                "",
                "§eClick para ver →");
        inv.setItem(20, particles);

        // Armor category
        ItemStack armor = createItem(Material.LEATHER_CHESTPLATE, "§d§l✦ Armaduras",
                "§7Armaduras coloridas",
                "§7que no cubren tu cabeza.",
                "",
                "§eClick para ver →");
        inv.setItem(22, armor);

        // Pets category
        ItemStack pets = createItem(Material.ARMOR_STAND, "§a§l✦ Mascotas",
                "§7Mini cabezas que levitan",
                "§7y te siguen por el lobby.",
                "",
                "§eClick para ver →");
        inv.setItem(24, pets);

        // Remove all cosmetics button
        ItemStack removeAll = createItem(Material.BARRIER, "§c§lQuitar Todo",
                "§7Desactiva todos tus cosméticos",
                "§7activos actualmente.",
                "",
                "§cClick para quitar →");
        inv.setItem(40, removeAll);

        player.openInventory(inv);
        player.playSound(player.getLocation(), Sound.BLOCK_CHEST_OPEN, 0.5f, 1.2f);
    }

    // ═══ Open Category Menu ═══
    public void openCategoryMenu(Player player, CosmeticType.CosmeticCategory category) {
        String title = switch(category) {
            case PARTICLES -> PARTICLES_TITLE;
            case PETS -> PETS_TITLE;
            case ARMOR -> ARMOR_TITLE;
        };
        Inventory inv = Bukkit.createInventory(null, 54, title);

        // Fill background
        ItemStack bg = createItem(Material.BLACK_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 54; i++) inv.setItem(i, bg);

        // Add cosmetic items
        CosmeticManager mgr = plugin.getCosmeticManager();
        int slot = 10;
        for (CosmeticType type : CosmeticType.values()) {
            if (type.getCategory() != category) continue;
            if (slot == 17) slot = 19; // Skip to next row
            if (slot == 26) slot = 28;
            if (slot == 35) slot = 37;

            boolean owned = mgr.ownsCosmetic(player, type);
            boolean active = mgr.isActive(player, type);

            List<String> lore = new ArrayList<>();
            lore.add("");
            if (active) {
                lore.add("§a§l✓ ACTIVADO");
                lore.add("");
                lore.add("§eClick para desactivar");
            } else if (owned) {
                lore.add("§7Estado: §aDesbloqueado");
                lore.add("");
                lore.add("§eClick para activar");
            } else {
                lore.add("§7Precio: §6" + type.getPrice() + " monedas");
                lore.add("");
                lore.add("§eClick para comprar");
            }

            Material icon = type.getIcon();
            if (active) {
                icon = Material.LIME_STAINED_GLASS_PANE;
            } else if (!owned) {
                icon = Material.GRAY_STAINED_GLASS_PANE;
            }

            String displayName = type.getDisplayName();
            if (!owned && type.getPrice() > 0) {
                displayName = "§8🔒 " + type.getName();
            }

            ItemStack item = createItem(icon, displayName, lore.toArray(new String[0]));
            
            // Add fake enchant to look cool for active armor
            if (active && category == CosmeticType.CosmeticCategory.ARMOR) {
                org.bukkit.inventory.meta.ItemMeta meta = item.getItemMeta();
                meta.addEnchant(org.bukkit.enchantments.Enchantment.UNBREAKING, 1, true);
                meta.addItemFlags(org.bukkit.inventory.ItemFlag.HIDE_ENCHANTS);
                item.setItemMeta(meta);
            }

            inv.setItem(slot, item);
            slot++;
        }

        // Back button
        ItemStack back = createItem(Material.ARROW, "§c← Volver",
                "§7Volver al menú principal");
        inv.setItem(49, back);

        player.openInventory(inv);
        player.playSound(player.getLocation(), Sound.UI_BUTTON_CLICK, 0.5f, 1.0f);
    }

    // ═══ Click Handler ═══
    @EventHandler
    public void onInventoryClick(InventoryClickEvent event) {
        if (!(event.getWhoClicked() instanceof Player player)) return;
        String title = event.getView().getTitle();

        if (!title.equals(MAIN_MENU_TITLE) && !title.equals(PARTICLES_TITLE) && !title.equals(PETS_TITLE) && !title.equals(ARMOR_TITLE)) return;

        event.setCancelled(true);

        ItemStack clicked = event.getCurrentItem();
        if (clicked == null || clicked.getType() == Material.BLACK_STAINED_GLASS_PANE) return;
        if (clicked.getType() == Material.AIR) return;

        CosmeticManager mgr = plugin.getCosmeticManager();

        // ── Main Menu ──
        if (title.equals(MAIN_MENU_TITLE)) {
            if (event.getSlot() == 20) {
                openCategoryMenu(player, CosmeticType.CosmeticCategory.PARTICLES);
            } else if (event.getSlot() == 22) {
                openCategoryMenu(player, CosmeticType.CosmeticCategory.ARMOR);
            } else if (event.getSlot() == 24) {
                openCategoryMenu(player, CosmeticType.CosmeticCategory.PETS);
            } else if (event.getSlot() == 40) {
                // Remove all
                mgr.removeAllCosmetics(player);
                player.closeInventory();
                player.sendMessage(Component.text("§c§l✖ §7Todos tus cosméticos han sido desactivados."));
                player.playSound(player.getLocation(), Sound.ENTITY_ITEM_BREAK, 0.8f, 0.8f);
            }
            return;
        }

        // ── Category Menus ──
        if (clicked.getType() == Material.ARROW) {
            openMainMenu(player);
            return;
        }

        // Find which cosmetic was clicked
        CosmeticType.CosmeticCategory category = switch (title) {
            case PARTICLES_TITLE -> CosmeticType.CosmeticCategory.PARTICLES;
            case PETS_TITLE -> CosmeticType.CosmeticCategory.PETS;
            default -> CosmeticType.CosmeticCategory.ARMOR;
        };

        int clickedSlot = event.getSlot();
        int index = 0;
        CosmeticType clickedType = null;

        int slot = 10;
        for (CosmeticType type : CosmeticType.values()) {
            if (type.getCategory() != category) continue;
            if (slot == 17) slot = 19;
            if (slot == 26) slot = 28;
            if (slot == 35) slot = 37;
            
            if (slot == clickedSlot) {
                clickedType = type;
                break;
            }
            slot++;
        }

        if (clickedType == null) return;

        // Handle click
        if (!mgr.ownsCosmetic(player, clickedType)) {
            // Try to purchase
            if (mgr.purchaseCosmetic(player, clickedType)) {
                player.sendMessage(Component.text("§a§l✓ §7¡Has desbloqueado " + clickedType.getDisplayName() + "§7!"));
                player.playSound(player.getLocation(), Sound.ENTITY_PLAYER_LEVELUP, 0.8f, 1.2f);
            } else {
                player.sendMessage(Component.text("§c§l✖ §7No tienes suficientes monedas."));
                player.playSound(player.getLocation(), Sound.ENTITY_VILLAGER_NO, 0.8f, 1.0f);
                return;
            }
        }

        // Toggle the cosmetic
        boolean nowActive = mgr.toggleCosmetic(player, clickedType);

        if (nowActive) {
            player.sendMessage(Component.text("§a§l✓ §7Has activado " + clickedType.getDisplayName() + "§7!"));
            player.playSound(player.getLocation(), Sound.BLOCK_NOTE_BLOCK_CHIME, 0.8f, 1.5f);
        } else {
            player.sendMessage(Component.text("§c§l✖ §7Has desactivado " + clickedType.getDisplayName() + "§7."));
            player.playSound(player.getLocation(), Sound.BLOCK_NOTE_BLOCK_BASS, 0.8f, 0.8f);
        }

        // Refresh the menu
        openCategoryMenu(player, category);
    }

    // ═══ Utility ═══
    private ItemStack createItem(Material material, String name, String... lore) {
        ItemStack item = new ItemStack(material);
        ItemMeta meta = item.getItemMeta();
        meta.setDisplayName(name);
        if (lore.length > 0) {
            List<String> loreList = new ArrayList<>();
            for (String line : lore) loreList.add(line);
            meta.setLore(loreList);
        }
        item.setItemMeta(meta);
        return item;
    }
}
