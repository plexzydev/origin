package dev.plexzy.prisongens.upgrades.menu;

import dev.plexzy.prisongens.PrisonGens;
import dev.plexzy.prisongens.upgrades.IslandUpgradeType;
import dev.plexzy.prisongens.upgrades.IslandUpgrades;
import dev.plexzy.prisongens.utils.GuiUtil;
import dev.plexzy.prisongens.utils.ItemBuilder;
import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryCloseEvent;
import org.bukkit.inventory.Inventory;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Menú GUI para ver y comprar mejoras de isla.
 */
public class UpgradesMenu implements Listener {

    private final PrisonGens plugin;
    private final Map<UUID, Inventory> openMenus = new HashMap<>();

    public UpgradesMenu(PrisonGens plugin) {
        this.plugin = plugin;
        Bukkit.getPluginManager().registerEvents(this, plugin);
    }

    public void open(Player player, UUID islandId) {
        Inventory inv = Bukkit.createInventory(null, 45, ChatColor.DARK_GRAY + "⬆ " + ChatColor.AQUA + "Mejoras de Isla");

        GuiUtil.fillBorders(inv, GuiUtil.DARK_GLASS);

        IslandUpgrades upgrades = plugin.getUpgradeManager().getUpgrades(islandId);

        // Slots donde irán las mejoras
        int[] slots = {10, 11, 12, 13, 14, 15, 16, 20, 21, 22};
        IslandUpgradeType[] types = IslandUpgradeType.values();

        for (int i = 0; i < types.length && i < slots.length; i++) {
            IslandUpgradeType type = types[i];
            int currentLevel = upgrades.getLevel(type);
            boolean maxed = upgrades.isMaxLevel(type);

            ItemBuilder builder = ItemBuilder.of(type.getIcon())
                    .name(type.getColoredName())
                    .lore(ChatColor.GRAY + type.getDescription(),
                          "",
                          ChatColor.GRAY + "Nivel actual: " + ChatColor.WHITE + currentLevel + ChatColor.DARK_GRAY + "/" + type.getMaxLevel());

            if (!maxed) {
                double cost = type.getMoneyCost(currentLevel);
                long tCost = type.getTokenCost(currentLevel);
                builder.lore(
                        "",
                        ChatColor.YELLOW + "Costo de mejora:",
                        ChatColor.GREEN + "  $" + String.format("%.0f", cost),
                        ChatColor.GOLD + "  " + tCost + " Tokens",
                        "",
                        ChatColor.YELLOW + "▶ Click para mejorar"
                );
            } else {
                builder.lore(
                        "",
                        ChatColor.GREEN + "✔ NIVEL MÁXIMO"
                );
            }

            inv.setItem(slots[i], builder.build());
        }

        // Info de la isla (decoración)
        inv.setItem(40, ItemBuilder.of(Material.PLAYER_HEAD)
                .name(ChatColor.AQUA + "Tu Isla")
                .lore(ChatColor.GRAY + "Progresa y mejora los", ChatColor.GRAY + "atributos de tu isla aquí.")
                .build());

        openMenus.put(player.getUniqueId(), inv);
        player.openInventory(inv);
    }

    @EventHandler
    public void onClick(InventoryClickEvent e) {
        if (!(e.getWhoClicked() instanceof Player player)) return;
        Inventory menu = openMenus.get(player.getUniqueId());
        if (menu == null || !e.getInventory().equals(menu)) return;

        e.setCancelled(true);

        int slot = e.getRawSlot();
        int[] slots = {10, 11, 12, 13, 14, 15, 16, 20, 21, 22};
        IslandUpgradeType[] types = IslandUpgradeType.values();

        for (int i = 0; i < slots.length; i++) {
            if (slot == slots[i] && i < types.length) {
                UUID islandId = plugin.getIslandManager().getIslandId(player);
                if (islandId != null) {
                    if (plugin.getUpgradeManager().purchaseUpgrade(player, islandId, types[i])) {
                        open(player, islandId); // Refrescar el menú
                    }
                }
                return;
            }
        }
    }

    @EventHandler
    public void onClose(InventoryCloseEvent e) {
        openMenus.remove(e.getPlayer().getUniqueId());
    }
}
