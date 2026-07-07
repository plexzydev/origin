package dev.plexzy.prisongens.enchants.menu;

import dev.plexzy.prisongens.PrisonGens;
import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.utils.EconomyUtil;
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
import org.bukkit.inventory.ItemStack;

import java.util.*;

public class PickaxeMenu implements Listener {

    private final PrisonGens plugin;
    private final Map<UUID, Inventory> openMenus = new HashMap<>();

    public PickaxeMenu(PrisonGens plugin) {
        this.plugin = plugin;
        Bukkit.getPluginManager().registerEvents(this, plugin);
    }

    public void open(Player player, ItemStack pickaxe) {
        Inventory inv = Bukkit.createInventory(null, 54, 
                ChatColor.DARK_GRAY + "⛏ " + ChatColor.AQUA + "Mejorar Pico");
        
        GuiUtil.fillBorders(inv, GuiUtil.DARK_GLASS);
        
        // Colocar el pico en el centro superior (slot 4)
        inv.setItem(4, pickaxe);
        
        // Listar todos los encantamientos disponibles
        List<CustomEnchant> allEnchants = new ArrayList<>(plugin.getEnchantManager().getAllEnchants().values());
        
        // Slots para encantamientos (interior del GUI)
        int[] slots = {19, 20, 21, 22, 23, 24, 25, 
                       28, 29, 30, 31, 32, 33, 34, 
                       37, 38, 39, 40, 41, 42, 43};
                       
        for (int i = 0; i < allEnchants.size() && i < slots.length; i++) {
            CustomEnchant enc = allEnchants.get(i);
            int currentLvl = plugin.getEnchantManager().getEnchantLevel(pickaxe, enc);
            boolean maxed = currentLvl >= enc.getMaxLevel();
            
            ItemBuilder builder = ItemBuilder.of(Material.ENCHANTED_BOOK)
                .name(enc.getDisplayName())
                .lore(ChatColor.GRAY + enc.getDescription(),
                      "",
                      ChatColor.GRAY + "Rareza: " + enc.getRarity().getColored(),
                      ChatColor.GRAY + "Nivel actual: " + ChatColor.WHITE + currentLvl + ChatColor.DARK_GRAY + "/" + enc.getMaxLevel());
                      
            if (!maxed) {
                double cost = enc.getCost(currentLvl);
                long tCost = enc.getTokenCost(currentLvl);
                builder.lore("",
                             ChatColor.YELLOW + "Costo de mejora:",
                             ChatColor.GREEN + "  $" + String.format("%.0f", cost),
                             ChatColor.GOLD + "  " + tCost + " Tokens",
                             "",
                             ChatColor.YELLOW + "▶ Click para comprar/mejorar");
            } else {
                builder.lore("", ChatColor.GREEN + "✔ NIVEL MÁXIMO");
            }
            
            inv.setItem(slots[i], builder.build());
        }

        openMenus.put(player.getUniqueId(), inv);
        player.openInventory(inv);
    }

    @EventHandler
    public void onClick(InventoryClickEvent e) {
        if (!(e.getWhoClicked() instanceof Player player)) return;
        Inventory menu = openMenus.get(player.getUniqueId());
        if (menu == null || !e.getInventory().equals(menu)) return;

        e.setCancelled(true);
        
        ItemStack clicked = e.getCurrentItem();
        if (clicked == null || clicked.getType() != Material.ENCHANTED_BOOK) return;
        
        // Obtener el pico (asumimos que sigue en la mano o en el slot 4)
        ItemStack pickaxe = player.getInventory().getItemInMainHand();
        if (!pickaxe.getType().toString().endsWith("PICKAXE")) {
            player.sendMessage("§c✘ Ya no tienes el pico en la mano principal.");
            player.closeInventory();
            return;
        }

        // Identificar el encantamiento por el nombre del item clickeado
        String itemName = clicked.getItemMeta().getDisplayName();
        CustomEnchant targetEnchant = null;
        for (CustomEnchant enc : plugin.getEnchantManager().getAllEnchants().values()) {
            if (enc.getDisplayName().equals(itemName)) {
                targetEnchant = enc;
                break;
            }
        }

        if (targetEnchant == null) return;

        int currentLvl = plugin.getEnchantManager().getEnchantLevel(pickaxe, targetEnchant);
        
        if (currentLvl >= targetEnchant.getMaxLevel()) {
            player.sendMessage("§c✘ ¡Este encantamiento ya está al nivel máximo!");
            return;
        }

        double cost = targetEnchant.getCost(currentLvl);
        long tCost = targetEnchant.getTokenCost(currentLvl);

        if (!EconomyUtil.has(player, cost)) {
            player.sendMessage("§c✘ Necesitas §f$" + String.format("%.0f", cost) + " §cpara mejorar esto.");
            return;
        }

        if (!plugin.getGenManager().hasTokens(player, tCost)) {
            player.sendMessage("§c✘ Necesitas §f" + tCost + " §cTokens para mejorar esto.");
            return;
        }

        // Cobrar
        EconomyUtil.withdraw(player, cost);
        plugin.getGenManager().removeTokens(player, tCost);

        // Aplicar mejora
        plugin.getEnchantManager().addEnchant(pickaxe, targetEnchant, currentLvl + 1);
        
        player.playSound(player.getLocation(), org.bukkit.Sound.BLOCK_ENCHANTMENT_TABLE_USE, 1f, 1.2f);
        player.sendMessage("§a✔ ¡Has mejorado §f" + targetEnchant.getDisplayName() + " §aal nivel §f" + (currentLvl + 1) + "§a!");
        
        // Refrescar menú
        open(player, pickaxe);
    }

    @EventHandler
    public void onClose(InventoryCloseEvent e) {
        openMenus.remove(e.getPlayer().getUniqueId());
    }
}
