package com.servermc.prisongens.managers;

import com.servermc.prisongens.PrisonGens;
import org.bukkit.*;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.event.block.Action;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.ItemFlag;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.scheduler.BukkitTask;

import java.io.File;
import java.io.IOException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public class GensManager implements Listener {

    private final PrisonGens plugin;
    private File dataFile;
    private FileConfiguration dataConfig;
    private BukkitTask regenTask;

    private final Map<UUID, List<GenData>> playerGens = new ConcurrentHashMap<>();

    public enum GenType {
        COBBLE(1, "Cobble Gen", Material.COBBLESTONE, Material.COBBLESTONE, 3, 1000, "§7"),
        IRON(2, "Iron Gen", Material.RAW_IRON, Material.IRON_ORE, 3, 5000, "§f"),
        GOLD(3, "Gold Gen", Material.RAW_GOLD, Material.GOLD_ORE, 4, 15000, "§6"),
        DIAMOND(4, "Diamond Gen", Material.DIAMOND, Material.DIAMOND_ORE, 5, 50000, "§b"),
        EMERALD(5, "Emerald Gen", Material.EMERALD, Material.EMERALD_ORE, 5, 150000, "§a"),
        NETHERITE(6, "Netherite Gen", Material.NETHERITE_SCRAP, Material.ANCIENT_DEBRIS, 6, 500000, "§4");

        public final int tier;
        public final String name;
        public final Material icon;
        public final Material mineBlock;
        public final int baseRadius;
        public final int price;
        public final String color;

        GenType(int tier, String name, Material icon, Material mineBlock, int baseRadius, int price, String color) {
            this.tier = tier; this.name = name; this.icon = icon; this.mineBlock = mineBlock;
            this.baseRadius = baseRadius; this.price = price; this.color = color;
        }
    }

    public static class GenData {
        public GenType type;
        public int level = 1;
        public boolean placed = false;

        public int getRadius() { return type.baseRadius + (level - 1); }
        public int getUpgradeCost() { return type.price * (level + 1); }
    }

    private static final String GENS_MENU = "§6§l⚒ Generadores ⚒";
    private static final String UPGRADE_MENU = "§b§l⬆ Mejorar Gen";

    public GensManager(PrisonGens plugin) {
        this.plugin = plugin;
        loadData();
    }

    // ═══ Gen Item Creation ═══

    public ItemStack createGenItem(GenType type, int level) {
        ItemStack item = new ItemStack(type.icon);
        ItemMeta meta = item.getItemMeta();
        meta.setDisplayName(type.color + "§l⛏ " + type.name + " §7[Nv." + level + "]");
        List<String> lore = new ArrayList<>();
        lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        lore.add("§7Tier: " + type.color + "★".repeat(type.tier));
        lore.add("§7Nivel: §f" + level);
        lore.add("§7Radio de mina: §f" + (type.baseRadius + (level - 1)) + "x" + (type.baseRadius + (level - 1)));
        lore.add("§7Bloque: " + type.color + type.mineBlock.name().replace("_", " "));
        lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        lore.add("");
        lore.add("§eClick derecho §7para mejorar");
        lore.add("§eColocar en el NPC §7para activar");
        meta.setLore(lore);
        meta.addItemFlags(ItemFlag.HIDE_ATTRIBUTES, ItemFlag.HIDE_ENCHANTS);

        org.bukkit.NamespacedKey typeKey = new org.bukkit.NamespacedKey(plugin, "gen_type");
        org.bukkit.NamespacedKey levelKey = new org.bukkit.NamespacedKey(plugin, "gen_level");
        meta.getPersistentDataContainer().set(typeKey, PersistentDataType.STRING, type.name());
        meta.getPersistentDataContainer().set(levelKey, PersistentDataType.INTEGER, level);

        item.setItemMeta(meta);
        return item;
    }

    public boolean isGenItem(ItemStack item) {
        if (item == null || !item.hasItemMeta()) return false;
        return item.getItemMeta().getPersistentDataContainer().has(
                new org.bukkit.NamespacedKey(plugin, "gen_type"), PersistentDataType.STRING);
    }

    public GenType getGenType(ItemStack item) {
        if (!isGenItem(item)) return null;
        String typeName = item.getItemMeta().getPersistentDataContainer().get(
                new org.bukkit.NamespacedKey(plugin, "gen_type"), PersistentDataType.STRING);
        try { return GenType.valueOf(typeName); } catch (Exception e) { return null; }
    }

    public int getGenLevel(ItemStack item) {
        if (!isGenItem(item)) return 1;
        return item.getItemMeta().getPersistentDataContainer().getOrDefault(
                new org.bukkit.NamespacedKey(plugin, "gen_level"), PersistentDataType.INTEGER, 1);
    }

    // ═══ NPC Click → Open Shop ═══

    public void openGensMenu(Player player) {
        Inventory inv = Bukkit.createInventory(null, 54, GENS_MENU);

        ItemStack bg = makeItem(Material.BLACK_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 54; i++) inv.setItem(i, bg);
        ItemStack border = makeItem(Material.ORANGE_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 9; i++) inv.setItem(i, border);
        for (int i = 45; i < 54; i++) inv.setItem(i, border);

        List<GenData> gens = playerGens.getOrDefault(player.getUniqueId(), new ArrayList<>());
        IslandManager.IslandData island = plugin.getIslandManager().getIsland(player);

        int[] slots = {20, 21, 22, 23, 24};
        int i = 0;
        for (GenType gen : GenType.values()) {
            if (i >= slots.length) break;

            GenData existing = gens.stream().filter(g -> g.type == gen).findFirst().orElse(null);

            List<String> lore = new ArrayList<>();
            lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
            lore.add("§7Tier: " + gen.color + "★".repeat(gen.tier));
            lore.add("§7Radio: §f" + gen.baseRadius + "x" + gen.baseRadius);
            lore.add("§7Bloque: " + gen.color + gen.mineBlock.name().replace("_", " "));
            lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");

            if (existing != null) {
                lore.add("§a§l✓ Ya lo tienes §7(Nv." + existing.level + ")");
                lore.add("");
                lore.add("§7Sacá el gen del NPC para");
                lore.add("§7upgradearlo con click derecho.");
            } else {
                lore.add("§7Precio: §a$" + plugin.getEconomyManager().formatBalance(gen.price));
                lore.add("");
                lore.add("§eClick para comprar");
            }

            ItemStack item = makeItem(gen.icon, gen.color + "§l⛏ " + gen.name, lore.toArray(new String[0]));
            inv.setItem(slots[i], item);
            i++;
        }

        // NETHERITE in second row if needed
        if (GenType.values().length > 5) {
            GenType gen = GenType.NETHERITE;
            GenData existing = gens.stream().filter(g -> g.type == gen).findFirst().orElse(null);
            List<String> lore = new ArrayList<>();
            lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
            lore.add("§7Tier: " + gen.color + "★".repeat(gen.tier));
            lore.add("§7Radio: §f" + gen.baseRadius + "x" + gen.baseRadius);
            lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
            if (existing != null) {
                lore.add("§a§l✓ Ya lo tienes §7(Nv." + existing.level + ")");
            } else {
                lore.add("§7Precio: §a$" + plugin.getEconomyManager().formatBalance(gen.price));
                lore.add(""); lore.add("§eClick para comprar");
            }
            inv.setItem(31, makeItem(gen.icon, gen.color + "§l⛏ " + gen.name, lore.toArray(new String[0])));
        }

        // Info
        inv.setItem(49, makeItem(Material.BOOK, "§e§lℹ Info",
                "", "§7Gens: §f" + gens.size() + "/" + (island != null ? island.maxGens : 3),
                "§7Usa §e/is settings §7para más slots."));

        player.openInventory(inv);
        player.playSound(player.getLocation(), Sound.BLOCK_CHEST_OPEN, 0.5f, 1.2f);
    }

    // ═══ Right-click gen item → Upgrade confirmation ═══

    @EventHandler
    public void onInteract(PlayerInteractEvent event) {
        if (event.getAction() != Action.RIGHT_CLICK_AIR && event.getAction() != Action.RIGHT_CLICK_BLOCK) return;
        ItemStack item = event.getItem();
        if (!isGenItem(item)) return;

        event.setCancelled(true);
        Player player = event.getPlayer();
        GenType type = getGenType(item);
        int level = getGenLevel(item);
        if (type == null) return;

        openUpgradeConfirmation(player, type, level);
    }

    private void openUpgradeConfirmation(Player player, GenType type, int currentLevel) {
        int cost = type.price * (currentLevel + 1);
        Inventory inv = Bukkit.createInventory(null, 27, UPGRADE_MENU);

        ItemStack bg = makeItem(Material.GRAY_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 27; i++) inv.setItem(i, bg);

        // Gen info center
        List<String> infoLore = new ArrayList<>();
        infoLore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        infoLore.add("§7Nivel actual: §f" + currentLevel);
        infoLore.add("§7Siguiente nivel: §f" + (currentLevel + 1));
        infoLore.add("§7Radio: §f" + (type.baseRadius + currentLevel - 1) + " → §a" + (type.baseRadius + currentLevel));
        infoLore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        infoLore.add("§7Costo: §a$" + plugin.getEconomyManager().formatBalance(cost));
        inv.setItem(13, makeItem(type.icon, type.color + "§l" + type.name + " Nv." + currentLevel, infoLore.toArray(new String[0])));

        // Confirm
        inv.setItem(11, makeItem(Material.LIME_STAINED_GLASS_PANE, "§a§l✓ MEJORAR", "", "§7Costo: §a$" + plugin.getEconomyManager().formatBalance(cost)));
        // Cancel
        inv.setItem(15, makeItem(Material.RED_STAINED_GLASS_PANE, "§c§l✖ CANCELAR"));

        player.openInventory(inv);
    }

    @EventHandler
    public void onInventoryClick(InventoryClickEvent event) {
        if (!(event.getWhoClicked() instanceof Player player)) return;
        String title = event.getView().getTitle();

        if (title.equals(GENS_MENU)) {
            event.setCancelled(true);
            handleGensPurchase(player, event.getSlot());
        } else if (title.equals(UPGRADE_MENU)) {
            event.setCancelled(true);
            handleUpgradeConfirm(player, event.getSlot());
        }
    }

    private void handleGensPurchase(Player player, int slot) {
        GenType clickedType = null;
        if (slot == 20) clickedType = GenType.COBBLE;
        else if (slot == 21) clickedType = GenType.IRON;
        else if (slot == 22) clickedType = GenType.GOLD;
        else if (slot == 23) clickedType = GenType.DIAMOND;
        else if (slot == 24) clickedType = GenType.EMERALD;
        else if (slot == 31) clickedType = GenType.NETHERITE;
        if (clickedType == null) return;

        List<GenData> gens = playerGens.computeIfAbsent(player.getUniqueId(), k -> new ArrayList<>());
        IslandManager.IslandData island = plugin.getIslandManager().getIsland(player);
        if (island == null) return;

        // Already owns this gen?
        GenType ft = clickedType;
        if (gens.stream().anyMatch(g -> g.type == ft)) {
            player.sendMessage("§c§l✖ §7Ya tienes este gen. Sacalo del NPC y upgradealo con click derecho.");
            player.playSound(player.getLocation(), Sound.ENTITY_VILLAGER_NO, 0.8f, 1.0f);
            return;
        }

        if (gens.size() >= island.maxGens) {
            player.sendMessage("§c§l✖ §7Alcanzaste el límite de gens. Mejora con /is settings.");
            player.playSound(player.getLocation(), Sound.ENTITY_VILLAGER_NO, 0.8f, 1.0f);
            return;
        }

        if (!plugin.getEconomyManager().removeBalance(player, EconomyManager.MONEY, clickedType.price)) {
            player.sendMessage("§c§l✖ §7No tienes suficiente dinero.");
            player.playSound(player.getLocation(), Sound.ENTITY_VILLAGER_NO, 0.8f, 1.0f);
            return;
        }

        GenData gen = new GenData();
        gen.type = clickedType;
        gen.level = 1;
        gen.placed = true;
        gens.add(gen);

        regenerateMine(player.getUniqueId());
        saveData();
        plugin.getEconomyManager().saveData();

        // Update world border
        plugin.getIslandManager().applyWorldBorder(player, island);

        player.sendMessage("§a§l✓ §7¡" + clickedType.name + " comprado y colocado!");
        player.playSound(player.getLocation(), Sound.ENTITY_EXPERIENCE_ORB_PICKUP, 0.8f, 1.2f);
        player.closeInventory();
    }

    private void handleUpgradeConfirm(Player player, int slot) {
        if (slot == 15) { player.closeInventory(); return; } // Cancel
        if (slot != 11) return; // Not confirm

        // Find the gen item in player's inventory
        for (int i = 0; i < player.getInventory().getSize(); i++) {
            ItemStack item = player.getInventory().getItem(i);
            if (isGenItem(item)) {
                GenType type = getGenType(item);
                int level = getGenLevel(item);
                if (type == null) continue;

                int cost = type.price * (level + 1);
                if (!plugin.getEconomyManager().removeBalance(player, EconomyManager.MONEY, cost)) {
                    player.sendMessage("§c§l✖ §7No tienes suficiente dinero ($" + plugin.getEconomyManager().formatBalance(cost) + ").");
                    player.playSound(player.getLocation(), Sound.ENTITY_VILLAGER_NO, 0.8f, 1.0f);
                    player.closeInventory();
                    return;
                }

                // Upgrade the item
                player.getInventory().setItem(i, createGenItem(type, level + 1));

                // Also update data
                List<GenData> gens = playerGens.getOrDefault(player.getUniqueId(), new ArrayList<>());
                GenType ft = type;
                gens.stream().filter(g -> g.type == ft).findFirst().ifPresent(g -> g.level = g.level + 1);
                saveData();
                plugin.getEconomyManager().saveData();

                player.sendMessage("§a§l✓ §7¡Gen mejorado a nivel " + (level + 1) + "!");
                player.playSound(player.getLocation(), Sound.ENTITY_PLAYER_LEVELUP, 0.8f, 1.2f);
                player.closeInventory();
                return;
            }
        }
        player.sendMessage("§c§l✖ §7No tienes un gen en tu inventario para mejorar.");
        player.closeInventory();
    }

    // ═══ Mine Regen ═══

    public int calculateMineRadius(UUID ownerUUID) {
        List<GenData> gens = playerGens.getOrDefault(ownerUUID, new ArrayList<>());
        if (gens.isEmpty()) return 3;
        int total = 0;
        for (GenData g : gens) {
            if (g.placed) total += g.getRadius();
        }
        return Math.max(3, Math.min(total, 16));
    }

    public void regenerateMine(UUID ownerUUID) {
        IslandManager.IslandData island = plugin.getIslandManager().getIsland(ownerUUID);
        if (island == null) return;

        List<GenData> gens = playerGens.getOrDefault(ownerUUID, new ArrayList<>());
        List<GenData> placedGens = gens.stream().filter(g -> g.placed).toList();
        if (placedGens.isEmpty()) return;

        int radius = calculateMineRadius(ownerUUID);

        // Rebuild mine shell to match radius
        plugin.getIslandManager().buildMineShell(island, radius);

        // Fill blocks
        World world = plugin.getIslandManager().getIslandWorld();
        Location mc = plugin.getIslandManager().getMineCenter(island);
        int mineX = mc.getBlockX();
        int mineY = mc.getBlockY();
        int mineZ = mc.getBlockZ();
        int depth = 14;

        List<Material> palette = new ArrayList<>();
        for (GenData g : placedGens) {
            for (int c = 0; c < g.level; c++) palette.add(g.type.mineBlock);
        }

        Random rng = new Random();
        for (int x = -radius; x <= radius; x++) {
            for (int z = -radius; z <= radius; z++) {
                for (int d = 1; d <= depth; d++) {
                    world.getBlockAt(mineX + x, mineY - d, mineZ + z).setType(
                            palette.get(rng.nextInt(palette.size())));
                }
            }
        }
    }

    public void deleteGens(UUID owner) {
        playerGens.remove(owner);
        saveData();
    }

    public void startRegenTask() {
        regenTask = Bukkit.getScheduler().runTaskTimer(plugin, () -> {
            for (Map.Entry<UUID, List<GenData>> entry : playerGens.entrySet()) {
                boolean hasPlaced = entry.getValue().stream().anyMatch(g -> g.placed);
                if (!hasPlaced) continue;
                Player owner = Bukkit.getPlayer(entry.getKey());
                if (owner != null && owner.isOnline()) {
                    regenerateMine(entry.getKey());
                }
            }
        }, 600L, 600L);
    }

    public void stopRegenTask() { if (regenTask != null) regenTask.cancel(); }

    // ═══ Persistence ═══

    private void loadData() {
        if (!plugin.getDataFolder().exists()) plugin.getDataFolder().mkdirs();
        dataFile = new File(plugin.getDataFolder(), "gens.yml");
        if (!dataFile.exists()) { try { dataFile.createNewFile(); } catch (IOException e) { e.printStackTrace(); } }
        dataConfig = YamlConfiguration.loadConfiguration(dataFile);

        if (dataConfig.contains("gens")) {
            var section = dataConfig.getConfigurationSection("gens");
            if (section != null) {
                for (String uuidStr : section.getKeys(false)) {
                    UUID uuid = UUID.fromString(uuidStr);
                    List<GenData> gens = new ArrayList<>();
                    var genSection = section.getConfigurationSection(uuidStr);
                    if (genSection != null) {
                        for (String genKey : genSection.getKeys(false)) {
                            GenData gen = new GenData();
                            try { gen.type = GenType.valueOf(genSection.getString(genKey + ".type", "COBBLE")); }
                            catch (Exception e) { gen.type = GenType.COBBLE; }
                            gen.level = genSection.getInt(genKey + ".level", 1);
                            gen.placed = genSection.getBoolean(genKey + ".placed", true);
                            gens.add(gen);
                        }
                    }
                    playerGens.put(uuid, gens);
                }
            }
        }
    }

    public void saveData() {
        dataConfig.set("gens", null);
        for (Map.Entry<UUID, List<GenData>> entry : playerGens.entrySet()) {
            int i = 0;
            for (GenData gen : entry.getValue()) {
                String path = "gens." + entry.getKey().toString() + "." + i;
                dataConfig.set(path + ".type", gen.type.name());
                dataConfig.set(path + ".level", gen.level);
                dataConfig.set(path + ".placed", gen.placed);
                i++;
            }
        }
        try { dataConfig.save(dataFile); } catch (IOException e) { e.printStackTrace(); }
    }

    public Map<UUID, List<GenData>> getPlayerGens() { return playerGens; }

    private ItemStack makeItem(Material mat, String name, String... lore) {
        ItemStack item = new ItemStack(mat);
        ItemMeta meta = item.getItemMeta();
        meta.setDisplayName(name);
        if (lore.length > 0) meta.setLore(Arrays.asList(lore));
        meta.addItemFlags(ItemFlag.HIDE_ATTRIBUTES, ItemFlag.HIDE_ENCHANTS);
        item.setItemMeta(meta);
        return item;
    }
}
